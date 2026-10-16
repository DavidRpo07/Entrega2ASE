"""Tests del inyector: verifican las 5 condiciones de 'falla configurable'.
Ejecutar desde la raíz del repo:  python3 -m unittest discover -s lab/tests -t .
"""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

import yaml

from lab.fallas.inyector import (ConfiguracionInvalida, FallaInyectada,
                                 Inyector, punto_de_falla)

CATALOGO = Path(__file__).resolve().parents[1] / "fallas" / "catalogo.yaml"


class Reloj:
    """Reloj y sleep falsos: los tests corren instantáneos y deterministas."""
    def __init__(self):
        self.t = 0.0
        self.dormido = []

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.dormido.append(s)
        self.t += s


def nuevo(**kw):
    r = Reloj()
    return Inyector(reloj=r, dormir=r.dormir, intervalo_recarga_s=0, instancia="api-1", **kw), r


def falla(**kw):
    base = {"id": "A1", "tipo": "latencia_fija", "target": "catalogo.validar_sku",
            "ms_fijos": 800, "probabilidad": 1.0, "semilla": 42}
    base.update(kw)
    return base


class TestCatalogo(unittest.TestCase):
    def test_las_8_fallas_son_validas_y_hay_2_por_familia(self):
        iny, _ = nuevo()
        datos = yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))["fallas"]
        familias = {}
        for d in datos:
            f = iny.activar(dict(d))
            familias.setdefault(f.familia, []).append(f.id)
        iny.kill_switch()
        self.assertEqual(len(datos), 8)
        self.assertEqual(sorted(len(v) for v in familias.values()), [2, 2, 2, 2])


class TestParametrizada(unittest.TestCase):
    def test_latencia_fija(self):
        iny, r = nuevo()
        iny.activar(falla())
        self.assertEqual(iny.punto("catalogo.validar_sku"), 800)
        self.assertAlmostEqual(r.dormido[0], 0.8)

    def test_probabilidad_aproximada(self):
        iny, _ = nuevo()
        iny.activar(falla(probabilidad=0.3))
        n = sum(iny.punto("catalogo.validar_sku") > 0 for _ in range(5000))
        self.assertAlmostEqual(n / 5000, 0.3, delta=0.03)

    def test_lognormal_tiene_cola_y_tope(self):
        iny, _ = nuevo()
        iny.activar(falla(id="A2", tipo="latencia_lognormal", target="logistica.reservar_franja",
                          mu=5.5, sigma=1.0, max_ms=10000))
        ms = sorted(iny.punto("logistica.reservar_franja") for _ in range(4000))
        p50, p99 = ms[2000], ms[3960]
        self.assertTrue(200 < p50 < 300, p50)        # mediana ≈ e^5.5 ≈ 245 ms
        self.assertGreater(p99, 2000)                 # cola larga
        self.assertLessEqual(ms[-1], 10000)

    def test_error_lanza_codigo_http(self):
        iny, _ = nuevo()
        iny.activar(falla(id="D2", tipo="error", target="ext_sap.notificar", codigo_http=503))
        with self.assertRaises(FallaInyectada) as ctx:
            iny.punto("ext_sap.notificar")
        self.assertEqual(ctx.exception.codigo_http, 503)

    def test_configuracion_invalida_se_rechaza(self):
        iny, _ = nuevo()
        for mala in (falla(probabilidad=1.5), falla(tipo="inventado"),
                     falla(porcentaje_trafico=120), falla(campo_raro=1),
                     falla(id="A2", tipo="latencia_lognormal", sigma=0)):
            with self.assertRaises(ConfiguracionInvalida):
                iny.activar(mala)

    def test_duracion_expira(self):
        iny, r = nuevo()
        iny.activar(falla(duracion_s=300))
        r.t += 299
        self.assertEqual(len(iny.activas()), 1)
        r.t += 1
        self.assertEqual(iny.activas(), [])
        self.assertEqual(iny.punto("catalogo.validar_sku"), 0)


class TestFocalizable(unittest.TestCase):
    def test_solo_afecta_su_target(self):
        iny, _ = nuevo()
        iny.activar(falla())
        self.assertEqual(iny.punto("proveedores.validar_contrato"), 0)
        self.assertEqual(iny.punto("catalogo.validar_sku"), 800)

    def test_comodin_de_modulo(self):
        iny, _ = nuevo()
        iny.activar(falla(target="catalogo.*"))
        self.assertEqual(iny.punto("catalogo.cualquier_cosa"), 800)
        self.assertEqual(iny.punto("logistica.reservar_franja"), 0)

    def test_porcentaje_de_trafico_es_estable_por_clave(self):
        iny, _ = nuevo()
        iny.activar(falla(porcentaje_trafico=30))
        afectadas = {k for k in range(2000) if iny.punto("catalogo.validar_sku", clave=str(k)) > 0}
        self.assertAlmostEqual(len(afectadas) / 2000, 0.3, delta=0.04)
        # la misma petición siempre cae del mismo lado
        iny.activar(falla(porcentaje_trafico=30))
        again = {k for k in range(2000) if iny.punto("catalogo.validar_sku", clave=str(k)) > 0}
        self.assertEqual(afectadas, again)

    def test_cpu_solo_en_su_instancia(self):
        iny, _ = nuevo()  # instancia api-1
        iny.activar({"id": "C1", "tipo": "cpu", "target": "api-2", "hilos": 1})
        self.assertNotIn("C1", iny._cpu_hilos)
        iny.activar({"id": "C1", "tipo": "cpu", "target": "api-1", "hilos": 1, "carga_cpu": 0.5})
        self.assertIn("C1", iny._cpu_hilos)
        hilos = iny._cpu_hilos["C1"]
        iny.kill_switch()
        for h in hilos:
            h.join(timeout=1)
        self.assertFalse(any(h.is_alive() for h in hilos))


class TestReversible(unittest.TestCase):
    def test_kill_switch_apaga_todo(self):
        iny, _ = nuevo()
        iny.activar(falla())
        iny.activar(falla(id="D2", tipo="error", target="ext_sap.notificar"))
        self.assertEqual(sorted(iny.kill_switch()), ["A1", "D2"])
        self.assertEqual(iny.punto("catalogo.validar_sku"), 0)
        iny.punto("ext_sap.notificar")  # ya no lanza

    def test_pausa_del_consumidor(self):
        iny, r = nuevo()
        iny.activar({"id": "C2", "tipo": "pausa", "target": "worker.outbox", "duracion_s": 180})
        self.assertTrue(iny.pausado("worker.outbox"))
        r.t += 180
        self.assertFalse(iny.pausado("worker.outbox"))


class TestSinRedespliegue(unittest.TestCase):
    def test_recarga_en_caliente_y_kill_switch_por_archivo(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "faults.yaml"
            ruta.write_text("fallas: []\n")
            iny, _ = nuevo(ruta_config=ruta)
            self.assertEqual(iny.punto("catalogo.validar_sku"), 0)

            ruta.write_text(yaml.safe_dump({"fallas": [falla()]}))
            os.utime(ruta, (time.time() + 1, time.time() + 1))
            self.assertEqual(iny.punto("catalogo.validar_sku"), 800)

            ruta.write_text(yaml.safe_dump({"kill_switch": True, "fallas": [falla()]}))
            os.utime(ruta, (time.time() + 2, time.time() + 2))
            self.assertEqual(iny.punto("catalogo.validar_sku"), 0)

    def test_archivo_del_repo_es_valido(self):
        iny, _ = nuevo(ruta_config=CATALOGO.parent.parent / "faults.yaml")
        self.assertEqual(iny.activas(), [])


class TestReproducible(unittest.TestCase):
    def secuencia(self, semilla):
        iny, _ = nuevo()
        iny.activar(falla(probabilidad=0.3, semilla=semilla))
        return [iny.punto("catalogo.validar_sku") for _ in range(500)]

    def test_misma_semilla_mismas_decisiones(self):
        self.assertEqual(self.secuencia(42), self.secuencia(42))
        self.assertNotEqual(self.secuencia(42), self.secuencia(7))


class TestIntegracion(unittest.TestCase):
    def test_decorador_y_contadores_y_observadores(self):
        iny, r = nuevo()
        eventos = []
        iny.observadores.append(lambda ev, f: eventos.append((ev, f.id)))

        @punto_de_falla("catalogo.validar_sku", inyector=iny)
        def validar():
            return "ok"

        iny.activar(falla())
        self.assertEqual(validar(), "ok")
        self.assertEqual(iny.estado()["contadores"]["A1"], 1)
        self.assertIn(("inyectada", "A1"), eventos)
        self.assertAlmostEqual(r.dormido[0], 0.8)

    def test_concurrencia(self):
        iny = Inyector(dormir=lambda s: None, instancia="api-1")
        iny.activar(falla(probabilidad=0.5))
        hilos = [threading.Thread(target=lambda: [iny.punto("catalogo.validar_sku") for _ in range(500)])
                 for _ in range(8)]
        for h in hilos: h.start()
        for h in hilos: h.join()
        self.assertAlmostEqual(iny.contadores["A1"] / 4000, 0.5, delta=0.05)


if __name__ == "__main__":
    unittest.main()

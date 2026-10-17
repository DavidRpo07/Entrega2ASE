"""Tests de las correcciones de la fase 4: circuit breaker, backoff, correcciones.yaml en
caliente y plazo (timeout) del inyector. Sin Docker:  make test-lab
"""
import tempfile
import threading
import unittest
from pathlib import Path

import yaml

from lab.fallas.inyector import FallaInyectada, Inyector, PlazoAgotado
from lab.resiliencia.backoff import espera_s
from lab.resiliencia.breaker import ABIERTO, CERRADO, SEMIABIERTO, CircuitBreaker
from lab.resiliencia.config import (ConfiguracionInvalida, Correcciones, SECCIONES, escribir_activas,
                                    normalizar)

PLANTILLA = Path(__file__).resolve().parents[1] / "correcciones.yaml"


class Reloj:
    def __init__(self):
        self.t = 0.0
        self.dormido = []

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.dormido.append(s)
        self.t += s


class TestBreaker(unittest.TestCase):
    def nuevo(self, **kw):
        r = Reloj()
        cambios = []
        b = CircuitBreaker("x", reloj=r, al_cambiar=lambda n, d, h: cambios.append((d, h)), **kw)
        return b, r, cambios

    def test_abre_tras_5_fallos_consecutivos(self):
        b, _, cambios = self.nuevo(fallos_para_abrir=5)
        for _ in range(4):
            self.assertTrue(b.permite())
            b.fallo()
        self.assertEqual(b.estado, CERRADO)
        b.permite()
        b.fallo()
        self.assertEqual(b.estado, ABIERTO)
        self.assertFalse(b.permite())
        self.assertEqual(b.rechazos, 1)
        self.assertEqual(cambios, [(CERRADO, ABIERTO)])

    def test_un_exito_reinicia_la_cuenta(self):
        b, _, _ = self.nuevo(fallos_para_abrir=5)
        for _ in range(4):
            b.fallo()
        b.exito()
        for _ in range(4):
            b.fallo()
        self.assertEqual(b.estado, CERRADO)

    def test_semiabierto_a_los_30_s_con_una_sola_prueba(self):
        b, r, _ = self.nuevo(fallos_para_abrir=1, semiabierto_tras_s=30)
        b.fallo()
        r.t += 29.9
        self.assertFalse(b.permite())
        r.t += 0.1
        self.assertEqual(b.estado, SEMIABIERTO)
        self.assertTrue(b.permite())      # la prueba
        self.assertFalse(b.permite())     # las demás esperan su resultado
        b.exito()
        self.assertEqual(b.estado, CERRADO)
        self.assertTrue(b.permite())

    def test_prueba_fallida_vuelve_a_abrir_otros_30_s(self):
        b, r, cambios = self.nuevo(fallos_para_abrir=1, semiabierto_tras_s=30)
        b.fallo()
        r.t += 30
        self.assertTrue(b.permite())
        b.fallo()
        self.assertEqual(b.estado, ABIERTO)
        r.t += 29
        self.assertFalse(b.permite())
        r.t += 1
        self.assertEqual(b.estado, SEMIABIERTO)
        self.assertEqual(cambios, [(CERRADO, ABIERTO), (ABIERTO, SEMIABIERTO), (SEMIABIERTO, ABIERTO),
                                   (ABIERTO, SEMIABIERTO)])

    def test_cancelar_libera_el_turno_de_prueba(self):
        b, r, _ = self.nuevo(fallos_para_abrir=1, semiabierto_tras_s=1)
        b.fallo()
        r.t += 1
        self.assertTrue(b.permite())
        b.cancelar()
        self.assertTrue(b.permite())

    def test_concurrencia_una_sola_prueba(self):
        b, r, _ = self.nuevo(fallos_para_abrir=1, semiabierto_tras_s=1)
        b.fallo()
        r.t += 1
        permitidos = []
        hilos = [threading.Thread(target=lambda: permitidos.append(b.permite())) for _ in range(50)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sum(permitidos), 1)


class TestBackoff(unittest.TestCase):
    def test_exponencial_con_jitter_acotado(self):
        for intento, base in ((1, 0.1), (2, 0.2), (3, 0.4)):
            for clave in range(200):
                e = espera_s(intento, clave)
                self.assertGreaterEqual(e, base)
                self.assertLess(e, base * 1.5)

    def test_reproducible_y_desfasado(self):
        self.assertEqual(espera_s(2, 113546), espera_s(2, 113546))
        self.assertGreater(len({round(espera_s(1, k), 6) for k in range(100)}), 90)

    def test_intento_invalido(self):
        with self.assertRaises(ValueError):
            espera_s(0, 1)


class TestCorrecciones(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ruta = Path(self.dir.name) / "correcciones.yaml"

    def tearDown(self):
        self.dir.cleanup()

    def test_plantilla_valida_y_todo_apagado(self):
        datos = normalizar(yaml.safe_load(PLANTILLA.read_text(encoding="utf-8")))
        self.assertEqual([s for s in SECCIONES if datos[s]["activa"]], [])
        self.assertEqual(datos["bulkhead"]["pool_escritura"] + datos["bulkhead"]["pool_lectura"], 5)
        self.assertEqual(datos["catalogo"]["timeout_ms"], 200)
        self.assertEqual(datos["catalogo"]["breaker"], {"fallos_para_abrir": 5, "semiabierto_tras_s": 30})
        self.assertEqual(datos["bulkhead"]["pool_timeout_ms"], 500)
        self.assertEqual(datos["bulkhead"]["lock_timeout_ms"], 1000)
        self.assertEqual(datos["worker"]["max_intentos"], 3)
        self.assertEqual(datos["experimentos"], {"A1": ["catalogo"], "A2": ["bulkhead"], "B1": ["bulkhead"],
                                                 "B2": ["bulkhead"], "D2": ["worker"]})

    def test_sin_archivo_todo_apagado(self):
        c = Correcciones(self.ruta, intervalo_recarga_s=0)
        self.assertEqual(c.activas(), [])

    def test_encender_y_apagar_en_caliente_con_observadores(self):
        c = Correcciones(self.ruta, intervalo_recarga_s=0)
        vistos = []
        c.observadores.append(lambda a, n: vistos.append(n["corrida"]))
        escribir_activas(self.ruta, PLANTILLA, ["catalogo"], "A1-corr_X")
        self.assertTrue(c.activa("catalogo"))
        self.assertFalse(c.activa("bulkhead"))
        escribir_activas(self.ruta, PLANTILLA, [], None)
        self.assertEqual(c.activas(), [])
        self.assertEqual(vistos, ["A1-corr_X", None])

    def test_misma_seleccion_otra_corrida_notifica(self):
        c = Correcciones(self.ruta, intervalo_recarga_s=0)
        vistos = []
        c.observadores.append(lambda a, n: vistos.append(n["corrida"]))
        escribir_activas(self.ruta, PLANTILLA, ["worker"], "r1")
        c.activas()
        escribir_activas(self.ruta, PLANTILLA, ["worker"], "r2")
        c.activas()
        self.assertEqual(vistos, ["r1", "r2"])   # breakers y caché se reinician en cada corrida

    def test_archivo_invalido_conserva_la_configuracion(self):
        c = Correcciones(self.ruta, intervalo_recarga_s=0)
        escribir_activas(self.ruta, PLANTILLA, ["bulkhead"], None)
        self.assertTrue(c.activa("bulkhead"))
        self.ruta.write_text("bulkhead: {activa: true, pool_lectura: -1}\n", encoding="utf-8")
        self.assertTrue(c.activa("bulkhead"))
        self.assertEqual(c.parametros("bulkhead")["pool_lectura"], 2)

    def test_validacion(self):
        for malo in ({"catalogo": {"timeout": 1}}, {"catalogo": {"activa": "si"}},
                     {"bulkhead": {"pool_lectura": 0}}, {"worker": {"max_intentos": 0}},
                     {"experimentos": {"A1": ["cache"]}}, {"worker": {"breaker": 3}}):
            with self.assertRaises(ConfiguracionInvalida, msg=malo):
                normalizar(malo)
        with self.assertRaises(ConfiguracionInvalida):
            escribir_activas(self.ruta, PLANTILLA, ["no_existe"], None)


class TestPlazo(unittest.TestCase):
    def nuevo(self):
        r = Reloj()
        return Inyector(reloj=r, dormir=r.dormir, intervalo_recarga_s=0, instancia="api-1"), r

    def test_latencia_mayor_que_el_plazo_corta_a_los_200_ms(self):
        iny, r = self.nuevo()
        iny.activar({"id": "A1", "tipo": "latencia_fija", "target": "catalogo.validar_sku", "ms_fijos": 800})
        with self.assertRaises(PlazoAgotado) as ctx:
            with iny.plazo(200):
                iny.punto("catalogo.validar_sku", clave="c1")
        self.assertAlmostEqual(r.t, 0.2)
        self.assertAlmostEqual(ctx.exception.esperado_ms, 200)

    def test_latencia_dentro_del_plazo_no_corta(self):
        iny, r = self.nuevo()
        iny.activar({"id": "A1", "tipo": "latencia_fija", "target": "catalogo.validar_sku", "ms_fijos": 150})
        with iny.plazo(200):
            self.assertEqual(iny.punto("catalogo.validar_sku", clave="c1"), 150)

    def test_sin_plazo_comportamiento_de_siempre(self):
        iny, r = self.nuevo()
        iny.activar({"id": "A1", "tipo": "latencia_fija", "target": "catalogo.validar_sku", "ms_fijos": 800})
        iny.punto("catalogo.validar_sku", clave="c1")
        self.assertAlmostEqual(r.t, 0.8)

    def test_error_dentro_del_plazo_sigue_siendo_error(self):
        iny, _ = self.nuevo()
        iny.activar({"id": "D2", "tipo": "error", "target": "x", "ms_fijos": 100})
        with self.assertRaises(FallaInyectada):
            with iny.plazo(200):
                iny.punto("x", clave="c1")

    def test_el_plazo_no_se_filtra_fuera_del_bloque(self):
        iny, r = self.nuevo()
        iny.activar({"id": "A1", "tipo": "latencia_fija", "target": "t", "ms_fijos": 800})
        with self.assertRaises(PlazoAgotado):
            with iny.plazo(200):
                iny.punto("t", clave="c1")
        iny.punto("t", clave="c1")   # ya sin plazo: duerme los 800 ms completos
        self.assertAlmostEqual(r.t, 1.0)


if __name__ == "__main__":
    unittest.main()

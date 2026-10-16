// Carga del laboratorio (Entregable 3): recorre en orden la secuencia generada por
// lab/carga/generar_carga.py (semilla fija), a tasa constante (open model: si el
// sistema se degrada, k6 no baja la tasa, como ocurre con clientes reales).
//
//   make lab-carga RATE=20 DURACION=2m
//
// Variables: BASE, CARGA (ruta del JSON), RATE (iteraciones/s), DURACION, VUS_MAX, ETIQUETA.
import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Trend } from 'k6/metrics';

const BASE = __ENV.BASE || 'http://nginx';
const items = new SharedArray('carga', () => JSON.parse(open(__ENV.CARGA)));

export const options = {
  scenarios: {
    carga: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 20),
      timeUnit: '1s',
      duration: __ENV.DURACION || '2m',
      preAllocatedVUs: Number(__ENV.VUS || 20),
      maxVUs: Number(__ENV.VUS_MAX || 1000),
    },
  },
  summaryTrendStats: ['min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  tags: { etiqueta: __ENV.ETIQUETA || 'sin_etiqueta' },
};

const latencia = {
  crear: new Trend('lat_crear', true),
  listar: new Trend('lat_listar', true),
  precio: new Trend('lat_precio', true),
};
// Un contador por código (0 = sin respuesta: timeout / conexión rechazada).
const CODIGOS = [200, 201, 404, 422, 429, 500, 502, 503, 504, 0];
const porCodigo = Object.fromEntries(CODIGOS.map((c) => [c, new Counter(`codigo_${c}`)]));
const otros = new Counter('codigo_otro');

const params = (op, i) => ({
  // X-Clave-Carga: el inyector decide por (semilla, falla, clave) → mismas peticiones afectadas.
  headers: { 'Content-Type': 'application/json', 'X-Clave-Carga': `c${i}` },
  tags: { op, clave: `c${i}` },
  timeout: __ENV.TIMEOUT || '60s',
});

export default function () {
  const i = exec.scenario.iterationInTest;
  const it = items[i % items.length];
  let r;
  if (it.op === 'crear') {
    r = http.post(`${BASE}/ordenes`, JSON.stringify(it.body), params('crear', i));
  } else if (it.op === 'listar') {
    r = http.get(`${BASE}/proveedores/${it.proveedor_id}/ordenes?offset=${it.offset}`, params('listar', i));
  } else {
    r = http.get(`${BASE}/catalogo/precio?proveedor_id=${it.proveedor_id}&sku_id=${it.sku_id}&fecha=${encodeURIComponent(it.fecha)}`, params('precio', i));
  }
  latencia[it.op].add(r.timings.duration);
  (porCodigo[r.status] || otros).add(1);
  check(r, { 'respuesta 2xx': (x) => x.status >= 200 && x.status < 300 });
}

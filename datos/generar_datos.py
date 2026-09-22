#!/usr/bin/env python3

import argparse
import csv
import random
import itertools
import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone


# ============================================================
# CONFIGURACIÓN GENERAL Y VOLUMETRÍA
# ============================================================

SEED = 42

NUM_PROVEEDORES = 100_000
NUM_CONTRATOS = 15_000

PORCENTAJE_PROVEEDORES_CON_CONTRATO = 0.12

NUM_SKUS = 400_000
NUM_ORDENES = 500_000
NUM_LINEAS = 3_000_000
NUM_FRANJAS = 150_000
NUM_AUDITORIAS = 800_000

ZIPF_S = 0.70

FECHA_INICIO = datetime(2025, 1, 1, tzinfo=timezone.utc)
FECHA_FIN = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
FECHA_REFERENCIA = datetime(2026, 9, 16, 0, 0, 0, tzinfo=timezone.utc)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "csv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTADOS_DIR = BASE_DIR / "resultados"

FECHA_CASO_VENCIDO = FECHA_REFERENCIA - timedelta(days=1)
FECHA_CASO_VENCE_HOY = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

MODELOS_POR_TIPO_PRODUCTO = {
    "alta_variedad": 1500,
    "media_variedad": 800,
    "baja_variedad": 300,
}

PREFIJOS_MARCA = [
    "Andina", "Nova", "Pro", "Max", "Global", "Central", "Integral", "Nacional",
    "Elite", "Avanza", "Suprema", "Prime", "Alianza", "Horizonte", "Continental",
    "Unión", "Universal", "Selecta", "Superior", "Moderna", "Aero", "Bio",
    "Crono", "Delta", "Eco", "Futura", "Geo", "Hyper", "Icon", "Krono",
    "Lumina", "Meta", "Nexus", "Omni", "Penta", "Quantum", "Royal", "Stellar",
    "Terra", "Vanguard", "Vita", "Zenith", "Apex", "Aura", "Dyna"
]

SUFIJOS_MARCA = [
    "Plus", "Pro", "Max", "Home", "Tech", "Market", "Solutions", "Group",
    "Brands", "Col", "Corp", "Line", "Pack", "System", "Smart", "Point",
    "Star", "Flex", "Soft", "Craft", "Wave", "Hub", "Lab", "Net", "Zone",
    "Core", "Link", "Works", "Way", "Base"
]

DESCRIPTORES_MARCA = [
    "Colombia", "Andina", "Latina", "Nacional", "Central", "Comercial",
    "Industrial", "Distribución", "Empresarial", "Corporativa", "Internacional",
    "Especializada", "Integral", "Líder", "Premium", "Global", "Operativa",
    "Estratégica", "Logística", "Directa"
]

CEDIS_BASE = [
    (1, "CEDI Central Bogotá", 50, "ACTIVO"),
    (2, "CEDI Norte Medellín", 40, "ACTIVO"),
    (3, "CEDI Occidente Cali", 35, "ACTIVO"),
    (4, "CEDI Caribe Barranquilla", 30, "ACTIVO"),
    (5, "CEDI Oriente Bucaramanga", 25, "ACTIVO"),
]


# ============================================================
# DICCIONARIOS Y MAESTROS DE CATÁLOGO
# ============================================================

PERFIL_PRODUCTO = {
    "Televisor": "alta_variedad", "Monitor": "alta_variedad", "Celular": "alta_variedad",
    "Tablet": "media_variedad", "Computador portátil": "alta_variedad", "Computador de escritorio": "media_variedad",
    "Impresora": "media_variedad", "Audífonos": "alta_variedad", "Router": "media_variedad",
    "Nevera": "media_variedad", "Lavadora": "media_variedad", "Microondas": "baja_variedad",
    "Licuadora": "media_variedad", "Cafetera": "media_variedad", "Freidora de aire": "media_variedad",
    "Aspiradora": "media_variedad", "Shampoo": "alta_variedad", "Acondicionador": "alta_variedad",
    "Crema dental": "alta_variedad", "Desodorante": "alta_variedad", "Gaseosa": "media_variedad",
    "Agua mineral": "baja_variedad", "Jugo": "media_variedad", "Cereal": "media_variedad",
    "Galletas": "alta_variedad", "Detergente líquido": "media_variedad", "Detergente en polvo": "media_variedad",
    "Papel higiénico": "baja_variedad", "Muñeca": "alta_variedad", "Carro de juguete": "alta_variedad",
    "Juego de mesa": "media_variedad", "Figura de acción": "alta_variedad", "Set de construcción": "alta_variedad",
    "Camiseta": "alta_variedad", "Jean": "alta_variedad", "Pijama": "media_variedad",
    "Ropa interior": "alta_variedad", "Medias": "media_variedad", "Bebida": "media_variedad",
    "Bebida energética": "media_variedad", "Bebida láctea": "media_variedad", "Café": "media_variedad",
    "Chocolate de mesa": "baja_variedad", "Cocina": "baja_variedad", "Crema corporal": "alta_variedad",
    "Desinfectante": "media_variedad", "Enjuague bucal": "media_variedad", "Horno eléctrico": "media_variedad",
    "Jabón corporal": "alta_variedad", "Leche en polvo": "media_variedad", "Limpiador multiusos": "media_variedad",
    "Maleta": "media_variedad", "Malta": "baja_variedad", "Mochila": "media_variedad",
    "Pan": "media_variedad", "Plancha": "media_variedad", "Proyector": "media_variedad",
    "Suavizante": "media_variedad", "Toallas de cocina": "baja_variedad", "Té listo para tomar": "media_variedad",
    "Yogur": "alta_variedad",
}

CODIGOS_CATEGORIA = {
    "alimentos": "ALI", "bebidas": "BEB", "aseo": "ASE", "cuidado_personal": "CUI",
    "tecnologia": "TEC", "hogar": "HOG", "juguetes": "JUG", "textil": "TEX",
}

PRODUCTOS_BASE = {
    "alimentos": ["Arroz", "Frijol", "Lentejas", "Pasta", "Harina de trigo", "Harina de maíz", "Aceite vegetal", "Azúcar", "Sal", "Atún en lata", "Galletas", "Cereal", "Chocolate de mesa", "Leche en polvo", "Salsa de tomate"],
    "bebidas": ["Gaseosa", "Agua mineral", "Agua con gas", "Jugo", "Néctar", "Bebida energética", "Bebida hidratante", "Té listo para tomar", "Café listo para tomar", "Malta"],
    "aseo": ["Detergente líquido", "Detergente en polvo", "Suavizante", "Jabón para ropa", "Lavaloza", "Limpiador multiusos", "Desinfectante", "Blanqueador", "Limpiavidrios", "Esponjas", "Bolsas para basura", "Papel higiénico", "Toallas de cocina"],
    "cuidado_personal": ["Shampoo", "Acondicionador", "Jabón corporal", "Jabón líquido", "Desodorante", "Crema dental", "Enjuague bucal", "Crema corporal", "Protector solar", "Máquina de afeitar"],
    "tecnologia": ["Televisor", "Monitor", "Computador portátil", "Computador de escritorio", "Tablet", "Celular", "Audífonos", "Teclado", "Mouse", "Impresora", "Proyector", "Router", "Disco externo", "Memoria USB", "Cámara web"],
    "hogar": ["Nevera", "Lavadora", "Microondas", "Licuadora", "Cafetera", "Freidora de aire", "Horno eléctrico", "Ventilador", "Plancha", "Aspiradora", "Juego de vasos", "Juego de platos", "Contenedor hermético", "Sartén", "Olla"],
    "juguetes": ["Muñeca", "Carro de juguete", "Set de construcción", "Rompecabezas", "Juego de mesa", "Pelota", "Pista de carros", "Juego de cocina", "Peluche", "Figura de acción"],
    "textil": ["Camiseta", "Camisa", "Jean", "Pantalón", "Short", "Vestido", "Chaqueta", "Ropa interior", "Medias", "Pijama", "Zapatos", "Sandalias"],
}

PRODUCTOS_POR_MARCA = {
    "Alpina": ["Leche en polvo", "Yogur", "Bebida láctea"],
    "Nestlé": ["Cereal", "Chocolate de mesa", "Galletas", "Leche en polvo"],
    "Bimbo": ["Pan", "Galletas"], "Casa Luker": ["Chocolate de mesa", "Café"],
    "Alquería": ["Leche en polvo", "Bebida láctea"], "Colanta": ["Leche en polvo", "Bebida láctea"],
    "Harinera del Valle": ["Pan", "Galletas"], "Levapan": ["Pan", "Cereal"],
    "Bavaria": ["Malta", "Agua mineral"], "Postobón": ["Gaseosa", "Agua mineral", "Jugo", "Té listo para tomar"],
    "Coca-Cola FEMSA": ["Gaseosa", "Agua mineral", "Bebida energética"], "Diageo": ["Bebida"],
    "LG": ["Televisor", "Monitor"], "Samsung": ["Televisor", "Monitor", "Tablet", "Celular"],
    "Motorola": ["Celular", "Tablet"], "Lenovo": ["Computador portátil", "Computador de escritorio", "Tablet", "Monitor"],
    "HP": ["Computador portátil", "Computador de escritorio", "Monitor", "Impresora"], "Acer": ["Computador portátil", "Monitor"],
    "ASUS": ["Computador portátil", "Monitor", "Router"], "Huawei": ["Celular", "Tablet", "Router"],
    "Epson": ["Impresora", "Proyector"], "Sony": ["Televisor", "Audífonos"],
    "Mabe": ["Nevera", "Lavadora", "Microondas"], "Haceb": ["Nevera", "Lavadora", "Microondas", "Horno eléctrico"],
    "Whirlpool": ["Nevera", "Lavadora", "Microondas"], "Oster": ["Licuadora", "Cafetera", "Freidora de aire"],
    "Electrolux": ["Nevera", "Lavadora", "Aspiradora"], "Indurama": ["Nevera", "Cocina", "Horno eléctrico"],
    "Black+Decker": ["Licuadora", "Freidora de aire", "Aspiradora", "Plancha"], "Groupe SEB": ["Licuadora", "Cafetera", "Freidora de aire", "Plancha"],
    "Cristar": ["Licuadora", "Microondas"], "Tablemac": ["Computador de escritorio"],
    "Procter & Gamble": ["Detergente líquido", "Suavizante", "Shampoo", "Desodorante"], "Unilever": ["Detergente líquido", "Suavizante", "Shampoo", "Desodorante", "Jabón corporal"],
    "Colgate-Palmolive": ["Crema dental", "Enjuague bucal", "Jabón corporal"], "Kimberly-Clark": ["Papel higiénico", "Toallas de cocina"],
    "Reckitt": ["Desinfectante", "Limpiador multiusos"], "Familia": ["Papel higiénico", "Toallas de cocina"],
    "L'Oréal": ["Shampoo", "Acondicionador", "Crema corporal"], "Mattel": ["Muñeca", "Carro de juguete", "Juego de mesa", "Figura de acción"],
    "Hasbro": ["Juego de mesa", "Figura de acción", "Set de construcción"], "Leonisa": ["Ropa interior", "Camiseta", "Pijama"],
    "Nalsani": ["Mochila", "Maleta", "Camiseta"], "Hermeco": ["Camiseta", "Jean", "Pijama"],
    "Crystal": ["Medias", "Ropa interior", "Camiseta"], "Cannon": ["Pijama", "Camiseta"],
    "Fantasía": ["Pijama", "Camiseta"], "Spring": ["Pijama"], "Eurocorsett": ["Ropa interior", "Pijama"],
    "Manufacturas Eliot": ["Camiseta", "Jean"],
}

FAMILIAS_PRODUCTO = {k: ["Estándar", "Premium", "Especial"] for k in PERFIL_PRODUCTO.keys()}
ATRIBUTOS_PRODUCTO = {k: ["Unidad 250g", "Unidad 500g", "Pack 1kg", "Estándar"] for k in PERFIL_PRODUCTO.keys()}

PROVEEDORES_BASE = [
    ("Alpina", "alimentos"), ("Bavaria", "bebidas"), ("LG Electronics Colombia", "tecnologia"),
    ("Samsung Electronics Colombia", "tecnologia"), ("Mabe Colombia", "hogar"), ("Motorola Mobility", "tecnologia"),
    ("Lenovo", "tecnologia"), ("HP Colombia", "tecnologia"), ("Industrias Haceb", "hogar"),
    ("Whirlpool Colombia", "hogar"), ("Oster de Colombia", "hogar"), ("Mattel Colombia", "juguetes"),
    ("Procter & Gamble Colombia", "aseo"), ("Unilever", "aseo"), ("Postobón", "bebidas"),
    ("Comercial Nutresa", "alimentos"), ("Colgate-Palmolive", "aseo"), ("Casa Luker", "alimentos"),
    ("Bimbo", "alimentos"), ("Nestlé", "alimentos"), ("Coca-Cola FEMSA", "bebidas"),
    ("Productos Familia", "aseo"), ("Alquería", "alimentos"), ("Cooperativa Colanta", "alimentos"),
    ("Harinera del Valle", "alimentos"), ("L'Oréal Colombia", "cuidado_personal"), ("Diageo Colombia", "bebidas"),
    ("Levapan", "alimentos"), ("Cristar", "hogar"), ("Industrias Cannon de Colombia", "hogar"),
    ("Industrias Fantasía", "hogar"), ("Tablemac", "hogar"), ("Spring", "hogar"),
    ("Nalsani", "textil"), ("Leonisa", "textil"), ("Hermeco", "textil"),
    ("Crystal", "textil"), ("Eurocorsett", "textil"), ("Manufacturas Eliot", "textil"),
    ("Acer América", "tecnologia"), ("ASUS", "tecnologia"), ("Huawei", "tecnologia"),
    ("Epson", "tecnologia"), ("Sony", "tecnologia"), ("Electrolux", "hogar"),
    ("Indurama", "hogar"), ("Kimberly-Clark", "aseo"), ("Reckitt", "aseo"),
    ("Black+Decker", "hogar"), ("Groupe SEB", "hogar"), ("Hasbro", "juguetes"),
]

# Ampliación masiva de tipos, nombres y ubicaciones para superar los 100.000 sintéticos únicos
TIPOS_EMPRESA = {
    "alimentos": [
        "Alimentos", "Distribuciones Alimentarias", "Productos Alimenticios",
        "Comercializadora de Alimentos", "Industrias Alimentarias", "Importadora de Alimentos"
    ],
    "bebidas": [
        "Bebidas", "Distribuciones de Bebidas", "Comercializadora de Bebidas",
        "Productos de Bebidas", "Industria de Bebidas", "Importadora de Bebidas"
    ],
    "tecnologia": [
        "Tecnología", "Soluciones Tecnológicas", "Importadora de Tecnología",
        "Comercializadora Tecnológica", "Distribuciones Tecnológicas", "Sistemas Tecnológicos"
    ],
    "hogar": [
        "Productos para el Hogar", "Industrias del Hogar", "Comercializadora del Hogar",
        "Importadora de Hogar", "Distribuciones para el Hogar", "Suministros del Hogar"
    ],
    "aseo": [
        "Productos de Aseo", "Industrias de Aseo", "Comercializadora de Aseo",
        "Distribuciones de Aseo", "Importadora de Aseo", "Suministros de Aseo"
    ],
    "cuidado_personal": [
        "Cuidado Personal", "Productos de Cuidado Personal",
        "Comercializadora de Cuidado Personal", "Distribuciones de Cuidado Personal",
        "Industrias de Cuidado Personal", "Importadora de Cuidado Personal"
    ],
    "textil": [
        "Textiles", "Industrias Textiles", "Comercializadora Textil",
        "Manufacturas Textiles", "Distribuciones Textiles", "Importadora Textil"
    ],
    "juguetes": [
        "Juguetes", "Industrias de Juguetes", "Comercializadora de Juguetes",
        "Importadora de Juguetes", "Distribuciones de Juguetes", "Novedades de Juguetes"
    ],
}

PROVEEDOR_POR_MARCA = {
    "Alpina": "Alpina", "Bavaria": "Bavaria", "LG": "LG Electronics Colombia",
    "Samsung": "Samsung Electronics Colombia", "Mabe": "Mabe Colombia", "Motorola": "Motorola Mobility",
    "Lenovo": "Lenovo", "HP": "HP Colombia", "Haceb": "Industrias Haceb",
    "Whirlpool": "Whirlpool Colombia", "Oster": "Oster de Colombia", "Mattel": "Mattel Colombia",
    "Procter & Gamble": "Procter & Gamble Colombia", "Unilever": "Unilever", "Postobón": "Postobón",
    "Nutresa": "Comercial Nutresa", "Colgate-Palmolive": "Colgate-Palmolive", "Casa Luker": "Casa Luker",
    "Bimbo": "Bimbo", "Nestlé": "Nestlé", "Coca-Cola FEMSA": "Coca-Cola FEMSA",
    "Familia": "Productos Familia", "Alquería": "Alquería", "Colanta": "Cooperativa Colanta",
    "Harinera del Valle": "Harinera del Valle", "L'Oréal": "L'Oréal Colombia", "Diageo": "Diageo Colombia",
    "Levapan": "Levapan", "Cristar": "Cristar", "Cannon": "Industrias Cannon de Colombia",
    "Fantasía": "Industrias Fantasía", "Tablemac": "Tablemac", "Spring": "Spring",
    "Nalsani": "Nalsani", "Leonisa": "Leonisa", "Hermeco": "Hermeco",
    "Crystal": "Crystal", "Eurocorsett": "Eurocorsett", "Manufacturas Eliot": "Manufacturas Eliot",
    "Acer": "Acer América", "ASUS": "ASUS", "Huawei": "Huawei",
    "Epson": "Epson", "Sony": "Sony", "Electrolux": "Electrolux",
    "Indurama": "Indurama", "Kimberly-Clark": "Kimberly-Clark", "Reckitt": "Reckitt",
    "Black+Decker": "Black+Decker", "Groupe SEB": "Groupe SEB", "Hasbro": "Hasbro"
}

NOMBRES_COMERCIALES = [
    "Andina", "La Montaña", "El Dorado", "Nueva Colombia", "Gran Colombia",
    "San Miguel", "Santa María", "Los Andes", "Valle", "Caribe", "Pacífico",
    "Oriente", "Occidente", "Central", "Metropolitana", "Nacional", "Continental",
    "Colombiana", "Americana", "Latina", "Imperial", "Real", "Nueva Era",
    "Progreso", "Futuro", "Horizonte", "Integral", "Unida", "Universal",
    "Principal", "Capital", "Premium", "Selecta", "Primera", "Gran Reserva",
    "Estrategia", "Avance", "Innovación", "Dinámica", "Moderna", "Vanguardia",
    "Soberana", "Triduo", "Estrella", "Cumbre"
]

UBICACIONES = [
    "Antioquia", "Medellín", "Bogotá", "Cali", "Barranquilla", "Cartagena",
    "Bucaramanga", "Pereira", "Manizales", "Armenia", "Ibagué", "Valle del Cauca",
    "Cundinamarca", "Atlántico", "Santander", "Risaralda", "Quindío", "Tolima",
    "Bolívar", "Córdoba", "Norte de Santander", "Boyacá", "Huila", "Meta",
    "Caldas", "Cesar", "Nariño", "Cauca", "Sucre", "La Guajira"
]

SUFIJOS_EMPRESA = ["S.A.S.", "S.A.", "Ltda."]


# ============================================================
# ETAPA 1: PROVEEDORES Y CONTRATOS
# ============================================================

def crear_rng(seed: int) -> random.Random:
    return random.Random(seed)

def generar_pool_nombres_sinteticos(rng: random.Random) -> list[tuple[str, str]]:
    """Genera un pool de 194.400 combinaciones deterministas únicas."""
    combinaciones = []
    nombres_base_set = {nombre for nombre, _ in PROVEEDORES_BASE}
    for sector, tipos in TIPOS_EMPRESA.items():
        for tipo in tipos:
            for nombre in NOMBRES_COMERCIALES:
                for ubicacion in UBICACIONES:
                    for sufijo in SUFIJOS_EMPRESA:
                        nombre_empresa = f"{tipo} {nombre} {ubicacion} {sufijo}"
                        if nombre_empresa not in nombres_base_set:
                            combinaciones.append((nombre_empresa, sector))
    rng.shuffle(combinaciones)
    return combinaciones

def generar_fecha_creacion(rng: random.Random) -> datetime:
    dias = rng.randint(0, 364)
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=dias)

def seleccionar_proveedores_con_contrato(rng: random.Random) -> list[int]:
    num_proveedores_con_contrato = round(NUM_PROVEEDORES * PORCENTAJE_PROVEEDORES_CON_CONTRATO)
    num_proveedores_reales = len(PROVEEDORES_BASE)
    proveedores_reales = list(range(1, num_proveedores_reales + 1))
    proveedores_sinteticos = list(range(num_proveedores_reales + 1, NUM_PROVEEDORES + 1))
    num_sinteticos_necesarios = num_proveedores_con_contrato - num_proveedores_reales
    seleccionados_sinteticos = rng.sample(proveedores_sinteticos, num_sinteticos_necesarios)
    proveedores_con_contrato = proveedores_reales + seleccionados_sinteticos
    rng.shuffle(proveedores_con_contrato)
    return proveedores_con_contrato

def asignar_cantidad_contratos(rng: random.Random, proveedores_con_contrato: list[int]) -> dict[int, int]:
    cantidades = {p_id: 1 for p_id in proveedores_con_contrato}
    contratos_restantes = NUM_CONTRATOS - len(proveedores_con_contrato)
    num_reales = len(PROVEEDORES_BASE)
    reales_seleccionados = [p_id for p_id in proveedores_con_contrato if p_id <= num_reales]

    for proveedor_id in reales_seleccionados:
        if contratos_restantes <= 0:
            break
        adicionales = min(rng.randint(1, 3), contratos_restantes)
        cantidades[proveedor_id] += adicionales
        contratos_restantes -= adicionales

    candidatos = proveedores_con_contrato.copy()
    while contratos_restantes > 0:
        proveedor_id = rng.choice(candidatos)
        cantidades[proveedor_id] += 1
        contratos_restantes -= 1

    return cantidades

def generar_periodo_contrato(rng, fecha_inicio_min=FECHA_INICIO, fecha_fin_max=FECHA_FIN, contratos_restantes=1):
    dias_disponibles = (fecha_fin_max - fecha_inicio_min).days
    if dias_disponibles < 1:
        raise ValueError("No hay días disponibles para generar el contrato.")
    dias_por_contrato = max(30, dias_disponibles // contratos_restantes)
    duracion_dias = dias_disponibles if contratos_restantes == 1 else min(rng.randint(30, dias_por_contrato + 30), dias_disponibles - (contratos_restantes - 1))
    fecha_inicio = fecha_inicio_min
    fecha_fin = fecha_inicio + timedelta(days=duracion_dias)
    return fecha_inicio, fecha_fin

def generar_contratos(rng, cantidades_contratos):
    ruta = OUTPUT_DIR / "contrato_suministro.csv"
    contrato_id = 1
    edge_proveedor_vencido = 1
    edge_proveedor_mediodia = 2

    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        writer = csv.writer(archivo)
        writer.writerow(["contrato_id", "proveedor_id", "numero_contrato", "fecha_inicio", "fecha_fin", "estado"])

        for proveedor_id, cantidad in cantidades_contratos.items():
            fecha_inicio_min = FECHA_INICIO
            for numero in range(1, cantidad + 1):
                contratos_restantes = cantidad - numero + 1
                if proveedor_id == edge_proveedor_vencido and numero == 1:
                    fecha_inicio = FECHA_CASO_VENCIDO - timedelta(days=180)
                    fecha_fin = FECHA_CASO_VENCIDO
                elif proveedor_id == edge_proveedor_mediodia and numero == 1:
                    fecha_inicio = FECHA_CASO_VENCE_HOY - timedelta(days=180)
                    fecha_fin = FECHA_CASO_VENCE_HOY
                else:
                    fecha_inicio, fecha_fin = generar_periodo_contrato(rng, fecha_inicio_min, FECHA_FIN, contratos_restantes)

                estado = "VENCIDO" if fecha_fin < FECHA_REFERENCIA else "VIGENTE"
                numero_contrato = f"CONT-{fecha_inicio.year}-{proveedor_id:06d}-{numero:02d}"
                writer.writerow([contrato_id, proveedor_id, numero_contrato, fecha_inicio.isoformat(), fecha_fin.isoformat(), estado])
                contrato_id += 1
                fecha_inicio_min = fecha_fin + timedelta(days=1)

    print(f"Contratos generados: {contrato_id - 1:,} -> {ruta}")

def generar_proveedores(rng: random.Random) -> dict[int, str]:
    archivo = OUTPUT_DIR / "proveedor.csv"
    pool_sinteticos = generar_pool_nombres_sinteticos(rng)
    idx_sintetico = 0
    sectores_por_proveedor = {}

    with archivo.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["proveedor_id", "nit", "nombre", "estado", "fecha_creacion"])

        for proveedor_id in range(1, NUM_PROVEEDORES + 1):
            if proveedor_id <= len(PROVEEDORES_BASE):
                nombre, sector = PROVEEDORES_BASE[proveedor_id - 1]
            else:
                nombre, sector = pool_sinteticos[idx_sintetico]
                idx_sintetico += 1

            sectores_por_proveedor[proveedor_id] = sector
            nit = f"{900000000 + proveedor_id}-1"
            prob = rng.random()
            estado = "ACTIVO" if prob < 0.90 else ("INACTIVO" if prob < 0.97 else "SUSPENDIDO")
            fecha_creacion = generar_fecha_creacion(rng)
            writer.writerow([proveedor_id, nit, nombre, estado, fecha_creacion.isoformat()])

    print(f"Proveedores generados: {NUM_PROVEEDORES:,} -> {archivo}")
    return sectores_por_proveedor

def generar_pool_marcas_sinteticas(rng: random.Random, marcas_usadas: set) -> list[str]:
    combinaciones = []
    for prefijo in PREFIJOS_MARCA:
        for sufijo in SUFIJOS_MARCA:
            for descriptor in DESCRIPTORES_MARCA:
                marca = f"{prefijo} {sufijo} {descriptor}"
                if marca not in marcas_usadas:
                    combinaciones.append(marca)
    rng.shuffle(combinaciones)
    return combinaciones

def construir_marcas_por_proveedor(rng: random.Random, proveedores_con_contrato: list[int]) -> dict[int, str]:
    marcas_por_proveedor = {}
    proveedor_a_marca_real = {prov_nombre: marca for marca, prov_nombre in PROVEEDOR_POR_MARCA.items()}
    marcas_usadas = set(PROVEEDOR_POR_MARCA.keys())
    num_reales = len(PROVEEDORES_BASE)

    for proveedor_id in range(1, num_reales + 1):
        if proveedor_id in proveedores_con_contrato:
            nombre_prov, _ = PROVEEDORES_BASE[proveedor_id - 1]
            if nombre_prov in proveedor_a_marca_real:
                marcas_por_proveedor[proveedor_id] = proveedor_a_marca_real[nombre_prov]

    pool_marcas = generar_pool_marcas_sinteticas(rng, marcas_usadas)
    idx_marca = 0

    for proveedor_id in proveedores_con_contrato:
        if proveedor_id not in marcas_por_proveedor:
            marca_sintetica = pool_marcas[idx_marca]
            idx_marca += 1
            marcas_por_proveedor[proveedor_id] = marca_sintetica
            marcas_usadas.add(marca_sintetica)

    return marcas_por_proveedor


# ============================================================
# ETAPA 2: CATALOGO (SKU Y CATALOGO NEGOCIADO)
# ============================================================

def generar_skus_y_catalogo(
    rng: random.Random,
    marcas_por_proveedor: dict[int, str],
    sectores_por_proveedor: dict[int, str]
):
    ruta_sku = OUTPUT_DIR / "sku.csv"
    ruta_cat = OUTPUT_DIR / "catalogo_negociado.csv"
    unidades_por_categoria = {
        "alimentos": ["g", "kg", "ml", "L", "unidad"], "bebidas": ["ml", "L", "six-pack"],
        "aseo": ["ml", "L", "g", "kg", "rollos"], "cuidado_personal": ["ml", "g", "unidad"],
        "tecnologia": ["unidad"], "hogar": ["unidad", "L"], "juguetes": ["unidad", "piezas"], "textil": ["unidad"]
    }

    sku_id = 1
    catalogo_id = 1
    num_reales = len(PROVEEDORES_BASE)
    skus_objetivo_por_proveedor = {}

    for p_id in range(1, num_reales + 1):
        if p_id in marcas_por_proveedor:
            skus_objetivo_por_proveedor[p_id] = 1000

    sinteticos_con_contrato = [p_id for p_id in marcas_por_proveedor if p_id > num_reales]
    skus_restantes = NUM_SKUS - (len(skus_objetivo_por_proveedor) * 1000)
    cuota_base = skus_restantes // len(sinteticos_con_contrato)
    residuo = skus_restantes % len(sinteticos_con_contrato)

    for idx, p_id in enumerate(sinteticos_con_contrato):
        skus_objetivo_por_proveedor[p_id] = cuota_base + (1 if idx < residuo else 0)

    with open(ruta_sku, "w", newline="", encoding="utf-8") as f_sku, \
         open(ruta_cat, "w", newline="", encoding="utf-8") as f_cat:

        w_sku = csv.writer(f_sku)
        w_cat = csv.writer(f_cat)
        w_sku.writerow(["sku_id", "codigo_sku", "nombre", "categoria", "unidad_medida"])
        w_cat.writerow(["catalogo_id", "sku_id", "proveedor_id", "precio", "fecha_inicio", "fecha_fin", "estado"])

        for proveedor_id, marca in marcas_por_proveedor.items():
            sector = sectores_por_proveedor[proveedor_id]
            cod_cat = CODIGOS_CATEGORIA.get(sector, "GEN")
            cod_marca = "".join([c for c in marca if c.isalnum()]).upper()[:3]
            if len(cod_marca) < 3:
                cod_marca = (cod_marca + "X")[:3]

            productos_disponibles = PRODUCTOS_BASE.get(sector, ["Producto General"])
            cuota_proveedor = skus_objetivo_por_proveedor[proveedor_id]
            skus_del_proveedor = []

            for i in range(1, cuota_proveedor + 1):
                producto = productos_disponibles[(i - 1) % len(productos_disponibles)]
                atributos = ATRIBUTOS_PRODUCTO.get(producto, ["Estándar"])
                atributo = atributos[(i - 1) % len(atributos)]
                prod_idx = ((i - 1) % len(productos_disponibles)) + 1
                var_idx = ((i - 1) % len(atributos)) + 1
                codigo_sku = f"{cod_cat}-{cod_marca}-{prod_idx:03d}-{var_idx:02d}-{sku_id:06d}"
                nombre_sku = f"{producto} {marca} Mod.{prod_idx} {atributo}"
                unidades = unidades_por_categoria.get(sector, ["unidad"])
                unidad = unidades[(i - 1) % len(unidades)]

                w_sku.writerow([sku_id, codigo_sku, nombre_sku, sector, unidad])
                skus_del_proveedor.append(sku_id)
                sku_id += 1

            # CASO BORDE 6: Proveedor ID 1 (Alpina) excluye 3 SKUs válidos de su catálogo negociado
            skus_a_negociar = skus_del_proveedor
            if proveedor_id == 1 and len(skus_del_proveedor) > 3:
                skus_a_negociar = skus_del_proveedor[:-3]

            for s_id in skus_a_negociar:
                precio = round(rng.uniform(15.0, 850.0), 2)
                w_cat.writerow([catalogo_id, s_id, proveedor_id, f"{precio:.2f}", FECHA_INICIO.isoformat(), FECHA_FIN.isoformat(), "ACTIVO"])
                catalogo_id += 1

    print(f"SKUs generados: {sku_id - 1:,} -> {ruta_sku}")
    print(f"Catálogo Negociado generado: {catalogo_id - 1:,} registros -> {ruta_cat}")


# ============================================================
# ETAPA 3: LOGÍSTICA (CEDI Y FRANJAS DE DESCARGUE)
# ============================================================

def generar_logistica(rng: random.Random):
    ruta_cedi = OUTPUT_DIR / "cedi.csv"
    ruta_franja = OUTPUT_DIR / "franja_descargue.csv"

    # 1. Guardar los CEDIs maestro
    with open(ruta_cedi, "w", newline="", encoding="utf-8") as f_cedi:
        w_cedi = csv.writer(f_cedi)
        w_cedi.writerow(["cedi_id", "nombre", "capacidad", "estado"])
        for cedi_id, nombre, capacidad, estado in CEDIS_BASE:
            w_cedi.writerow([cedi_id, nombre, capacidad, estado])

    print(f"CEDIs generados: {len(CEDIS_BASE)} -> {ruta_cedi}")

    # 2. Configuración de franjas horarias (35 bloques de 20 min por CEDI al día)
    fecha_inicio_logistica = datetime(2025, 1, 1).date()
    dias_totales = 730  # 24 meses
    horarios_inicio = []
    hora_actual = datetime.strptime("06:00", "%H:%M")
    hora_limite = datetime.strptime("17:20", "%H:%M")

    while hora_actual <= hora_limite:
        fin_bloque = hora_actual + timedelta(minutes=20)
        horarios_inicio.append((hora_actual.time(), fin_bloque.time()))
        hora_actual = fin_bloque

    # 3. Definir la cuota global de franjas completas
    # Queremos ~10.000 franjas completas en total para todo el dataset (~8% del total de 127.750 franjas)
    TOTAL_FRANJAS_COMPLETAS_OBJETIVO = 10_000
    CUOTA_PICO_FIN_MES = int(TOTAL_FRANJAS_COMPLETAS_OBJETIVO * 0.25)     # Exactamente 2.500 en picos
    CUOTA_RESTO_MES = TOTAL_FRANJAS_COMPLETAS_OBJETIVO - CUOTA_PICO_FIN_MES # Exactamente 7.500 en resto de días

    # Clasificar previamente los días de los 24 meses
    dias_pico = []
    dias_normales = []

    for d in range(dias_totales):
        fecha_curr = fecha_inicio_logistica + timedelta(days=d)
        dt_curr = datetime.combine(fecha_curr, datetime.min.time())
        if es_ultimo_tres_dias_habiles(dt_curr):
            dias_pico.append(fecha_curr.isoformat())
        else:
            dias_normales.append(fecha_curr.isoformat())

    # Calcular franjas totales por grupo de días (5 CEDIs * 35 bloques por día)
    total_slots_pico = len(dias_pico) * len(CEDIS_BASE) * len(horarios_inicio)
    total_slots_normales = len(dias_normales) * len(CEDIS_BASE) * len(horarios_inicio)

    # Probabilidades exactas para cumplir la cuota del 25% vs 75%
    prob_completar_pico = CUOTA_PICO_FIN_MES / total_slots_pico
    prob_completar_normal = CUOTA_RESTO_MES / total_slots_normales

    franja_id = 1
    franjas_completas_pico = 0
    franjas_completas_normal = 0

    with open(ruta_franja, "w", newline="", encoding="utf-8") as f_franja:
        w_franja = csv.writer(f_franja)
        w_franja.writerow(["franja_id", "cedi_id", "fecha", "hora_inicio", "hora_fin", "capacidad", "reservas_actuales", "estado"])

        for d in range(dias_totales):
            fecha_curr = fecha_inicio_logistica + timedelta(days=d)
            fecha_str = fecha_curr.isoformat()
            dt_curr = datetime.combine(fecha_curr, datetime.min.time())
            es_pico = es_ultimo_tres_dias_habiles(dt_curr)

            for cedi_id, _, _, _ in CEDIS_BASE:
                for h_ini, h_fin in horarios_inicio:
                    capacidad_franja = rng.randint(5, 12)
                    prob_actual = prob_completar_pico if es_pico else prob_completar_normal
                    
                    # Decidir si esta franja nace 'COMPLETA' o 'DISPONIBLE'
                    if rng.random() < prob_actual:
                        reservas = capacidad_franja
                        estado_franja = "COMPLETA"
                        if es_pico:
                            franjas_completas_pico += 1
                        else:
                            franjas_completas_normal += 1
                    else:
                        reservas = rng.randint(0, max(0, capacidad_franja - 2))
                        estado_franja = "DISPONIBLE"

                    # CASO BORDE 4: Mantener explícito el caso borde de 1 cupo libre en CEDI 1
                    if cedi_id == 1 and fecha_str == "2026-09-16" and h_ini.strftime("%H:%M:%S") == "08:00:00":
                        capacidad_franja = 10
                        reservas = 9
                        estado_franja = "DISPONIBLE"

                    w_franja.writerow([franja_id, cedi_id, fecha_str, h_ini.strftime("%H:%M:%S"), h_fin.strftime("%H:%M:%S"), capacidad_franja, reservas, estado_franja])
                    franja_id += 1

    total_completas = franjas_completas_pico + franjas_completas_normal
    pct_pico = (franjas_completas_pico / total_completas) * 100 if total_completas > 0 else 0

    print(f"Franjas de descargue generadas: {franja_id - 1:,} -> {ruta_franja}")
    print(f"  -> Franjas COMPLETA en Fin de Mes: {franjas_completas_pico:,} ({pct_pico:.2f}%)")
    print(f"  -> Franjas COMPLETA en Resto de Días: {franjas_completas_normal:,} ({100 - pct_pico:.2f}%)")
# ============================================================
# ETAPA 4 Y 5: ÓRDENES, LÍNEAS DE ORDEN Y AUDITORÍA
# ============================================================

def es_ultimo_tres_dias_habiles(fecha: datetime) -> bool:
    if fecha.month == 12:
        ultimo_dia = datetime(fecha.year + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo_dia = datetime(fecha.year, fecha.month + 1, 1) - timedelta(days=1)

    dias_habiles = []
    curr = ultimo_dia
    while len(dias_habiles) < 3 and curr.month == fecha.month:
        if curr.weekday() < 5:
            dias_habiles.append(curr.date())
        curr -= timedelta(days=1)

    return fecha.date() in dias_habiles

def generar_fecha_orden_estacional(rng: random.Random) -> datetime:
    dias_totales = 730
    dia_offset = rng.randint(0, dias_totales - 1)
    fecha_base = FECHA_INICIO + timedelta(days=dia_offset)

    if not es_ultimo_tres_dias_habiles(fecha_base) and rng.random() < 0.25:
        year, month = fecha_base.year, fecha_base.month
        u_dia = datetime(year + 1, 1, 1) - timedelta(days=1) if month == 12 else datetime(year, month + 1, 1) - timedelta(days=1)
        offset_fin = rng.choice([0, 1, 2])
        fecha_base = u_dia - timedelta(days=offset_fin)

    if rng.random() < 0.65:
        hora = rng.randint(8, 10)
    else:
        hora = rng.choice([6, 7, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])

    return fecha_base.replace(hour=hora, minute=rng.randint(0, 59), second=rng.randint(0, 59))

def generar_ordenes_lineas_y_auditoria(
    rng: random.Random,
    proveedores_con_contrato: list[int],
    sectores_por_proveedor: dict[int, str]
    ):
    ruta_orden = OUTPUT_DIR / "orden_compra.csv"
    ruta_linea = OUTPUT_DIR / "linea_orden.csv"
    ruta_audit = OUTPUT_DIR / "evento_auditoria.csv"
    ruta_cat = OUTPUT_DIR / "catalogo_negociado.csv"
    ruta_sku = OUTPUT_DIR / "sku.csv"

    skus_por_proveedor = {}
    precios_por_sku = {}
    with open(ruta_cat, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p_id = int(r["proveedor_id"])
            s_id = int(r["sku_id"])
            p = float(r["precio"])
            skus_por_proveedor.setdefault(p_id, []).append(s_id)
            precios_por_sku[(p_id, s_id)] = p

    categorias_sku = {}
    with open(ruta_sku, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            categorias_sku[int(r["sku_id"])] = r["categoria"]

    n_provs = len(proveedores_con_contrato)
    pesos_zipf = [1.0 / (i ** ZIPF_S) for i in range(1, n_provs + 1)]
    cum_zipf = list(itertools.accumulate(pesos_zipf))

    estados_orden = ["PENDIENTE", "EN_VALIDACION", "CONFIRMADA", "RECHAZADA", "CANCELADA"]
    cum_estados = list(itertools.accumulate([0.05, 0.10, 0.70, 0.10, 0.05]))

    opciones_lineas = [1, 2, 3, 4, 5, 6, 8, 10, 15, 25]
    cum_lineas = list(itertools.accumulate([15, 20, 20, 15, 10, 8, 5, 4, 2, 1]))

    linea_id = 1
    auditoria_id = 1

    with open(ruta_orden, "w", newline="", encoding="utf-8") as f_ord, \
         open(ruta_linea, "w", newline="", encoding="utf-8") as f_lin, \
         open(ruta_audit, "w", newline="", encoding="utf-8") as f_aud:

        w_ord = csv.writer(f_ord)
        w_lin = csv.writer(f_lin)
        w_aud = csv.writer(f_aud)

        # Encabezados exactos según la estructura DDL de PostgreSQL
        w_ord.writerow(["orden_id", "proveedor_id", "cedi_id", "fecha_creacion", "fecha_entrega_solicitada", "fecha_recepcion", "estado", "total"])
        w_lin.writerow(["linea_orden_id", "orden_id", "sku_id", "categoria", "cantidad_solicitada", "cantidad_recibida", "precio_unitario"])
        w_aud.writerow(["evento_id", "modulo", "entidad", "entidad_id", "tipo_evento", "estado_anterior", "estado_nuevo", "fecha_evento", "detalle"])

        for orden_id in range(1, NUM_ORDENES + 1):
            p_id = rng.choices(proveedores_con_contrato, cum_weights=cum_zipf, k=1)[0]
            fecha_creacion = generar_fecha_orden_estacional(rng)

            if p_id == 10 and fecha_creacion.year == 2026 and fecha_creacion.month == 6:
                p_id = 3

            cedi_id = rng.randint(1, 5)
            estado = rng.choices(estados_orden, cum_weights=cum_estados, k=1)[0]

            dias_entrega = rng.randint(2, 5)
            fecha_entrega_solicitada = fecha_creacion + timedelta(days=dias_entrega)
            
            if estado == "CONFIRMADA":
                fecha_recepcion = (fecha_entrega_solicitada + timedelta(hours=rng.randint(-12, 12))).isoformat()
            else:
                fecha_recepcion = ""

            num_lineas = 300 if orden_id == 1 else rng.choices(opciones_lineas, cum_weights=cum_lineas, k=1)[0]

            skus_disponibles = skus_por_proveedor.get(p_id, [1])
            num_hot_skus = max(1, int(len(skus_disponibles) * 0.10))
            hot_skus = skus_disponibles[:num_hot_skus]
            tail_skus = skus_disponibles[num_hot_skus:]

            monto_total = 0.0

            for _ in range(num_lineas):
                # (42% probabilidad de SKU Hot para compensar el efecto Zipf global):
                sku_id = (
                    rng.choice(tail_skus)
                    if (tail_skus and rng.random() > 0.42)
                    else rng.choice(hot_skus)
                )
                cantidad_sol = rng.randint(5, 200)
                cantidad_rec = cantidad_sol if estado == "CONFIRMADA" else 0
                precio_unitario = precios_por_sku.get((p_id, sku_id), 50.0)
                subtotal = round(cantidad_sol * precio_unitario, 2)
                monto_total += subtotal
                cat_snap = categorias_sku.get(sku_id, sectores_por_proveedor[p_id])

                w_lin.writerow([linea_id, orden_id, sku_id, cat_snap, cantidad_sol, cantidad_rec, f"{precio_unitario:.2f}"])
                linea_id += 1

            w_ord.writerow([orden_id, p_id, cedi_id, fecha_creacion.isoformat(), fecha_entrega_solicitada.isoformat(), fecha_recepcion, estado, f"{monto_total:.2f}"])

            if auditoria_id <= NUM_AUDITORIAS:
                detalle_json = f'{{"mensaje": "Orden {orden_id} creada"}}'
                w_aud.writerow([auditoria_id, "ordenes", "orden_compra", str(orden_id), "ORDEN_CREADA", "", estado, fecha_creacion.isoformat(), detalle_json])
                auditoria_id += 1

        while auditoria_id <= NUM_AUDITORIAS:
            fecha_audit = FECHA_INICIO + timedelta(days=rng.randint(0, 700))
            detalle_json = '{"mensaje": "Auditoria de contrato"}'
            w_aud.writerow([auditoria_id, "proveedores", "contrato_suministro", str(rng.randint(1, NUM_CONTRATOS)), "CONTRATO_REVISADO", "VIGENTE", "VIGENTE", fecha_audit.isoformat(), detalle_json])
            auditoria_id += 1

    print(f"Órdenes generadas: {NUM_ORDENES:,} -> {ruta_orden}")
    print(f"Líneas de orden generadas: {linea_id - 1:,} -> {ruta_linea}")
    print(f"Eventos de auditoría generados: {auditoria_id - 1:,} -> {ruta_audit}")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Generador determinista de datos para Entregable 2")
    parser.add_argument("--seed", type=int, default=SEED, help="Semilla del generador (por defecto: 42)")
    args = parser.parse_args()

    inicio_total = time.perf_counter()
    rng = crear_rng(args.seed)

    print("==============================================")
    print("Generador de datos - Entregable 2 (Completo)")
    print("==============================================")
    print(f"Seed: {args.seed}")
    print(f"Directorio de salida: {OUTPUT_DIR}\n")

    sectores_por_proveedor = generar_proveedores(rng)
    proveedores_con_contrato = seleccionar_proveedores_con_contrato(rng)
    cantidades_contratos = asignar_cantidad_contratos(rng, proveedores_con_contrato)
    generar_contratos(rng, cantidades_contratos)
    marcas_por_proveedor = construir_marcas_por_proveedor(rng, proveedores_con_contrato)
    generar_skus_y_catalogo(rng, marcas_por_proveedor, sectores_por_proveedor)
    generar_logistica(rng)
    generar_ordenes_lineas_y_auditoria(rng, proveedores_con_contrato, sectores_por_proveedor)

    # Evidencia: filas y tamaño por archivo, con tiempo total de generación.
    archivos = [
        "proveedor.csv", "contrato_suministro.csv", "sku.csv", "catalogo_negociado.csv",
        "cedi.csv", "franja_descargue.csv", "orden_compra.csv", "linea_orden.csv",
        "evento_auditoria.csv",
    ]
    duracion_s = time.perf_counter() - inicio_total
    RESULTADOS_DIR.mkdir(exist_ok=True)
    reporte = RESULTADOS_DIR / "generacion.csv"
    with reporte.open("w", newline="", encoding="utf-8") as salida:
        escritor = csv.DictWriter(salida, fieldnames=["archivo", "filas", "tamano_bytes", "duracion_total_s", "semilla"])
        escritor.writeheader()
        for nombre in archivos:
            ruta = OUTPUT_DIR / nombre
            with ruta.open("r", encoding="utf-8") as entrada:
                filas = sum(1 for _ in entrada) - 1
            escritor.writerow({"archivo": nombre, "filas": filas, "tamano_bytes": os.path.getsize(ruta),
                              "duracion_total_s": f"{duracion_s:.6f}", "semilla": args.seed})

    print(f"Tiempo total de generación: {duracion_s:.2f} s")
    print(f"Reporte de generación: {reporte}")
    print("\n¡Generación de todos los archivos CSV finalizada con éxito!")


if __name__ == "__main__":
    main()

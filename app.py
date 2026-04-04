import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
from typing import Tuple, Dict, Any


# ==========================
# Configuración general
# ==========================

SPREADSHEET_NAME = "Gastos Compartidos"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def formatear_cop(valor: Any) -> str:
    """Formatea un número como pesos colombianos."""
    try:
        numero = float(valor)
    except Exception:
        return "-"
    return f"${numero:,.0f}".replace(",", ".")


@st.cache_resource
def get_spreadsheet():
    """Conecta a Google Sheets usando credenciales en st.secrets."""
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    client = gspread.authorize(credentials)
    spreadsheet = client.open(SPREADSHEET_NAME)
    ensure_worksheets(spreadsheet)
    return spreadsheet


def get_worksheet(sheet_name: str):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)


def ensure_worksheets(spreadsheet):
    """Crea las hojas necesarias si no existen."""
    from gspread.exceptions import WorksheetNotFound

    # Hoja de gastos
    try:
        ws_gastos = spreadsheet.worksheet("gastos")
    except WorksheetNotFound:
        ws_gastos = spreadsheet.add_worksheet(title="gastos", rows=1000, cols=20)
        ws_gastos.append_row(
            [
                "id",
                "fecha",
                "descripcion",
                "monto",
                "quien_pago",
                "categoria",
                "subcategoria",
                "tipo_division",
                "porcentaje_persona1",
                "porcentaje_persona2",
                "created_at",
                "viaje_id",
            ]
        )
    else:
        # Asegurar columna viaje_id al final si no existe
        header = ws_gastos.row_values(1)
        if "viaje_id" not in header:
            ws_gastos.update_cell(1, len(header) + 1, "viaje_id")

    # Hoja de pagos
    try:
        ws_pagos = spreadsheet.worksheet("pagos")
    except WorksheetNotFound:
        ws_pagos = spreadsheet.add_worksheet(title="pagos", rows=1000, cols=20)
        ws_pagos.append_row(
            [
                "id",
                "fecha",
                "quien_paga",
                "quien_recibe",
                "monto",
                "categoria",
                "nota",
                "created_at",
                "viaje_id",
            ]
        )
    else:
        header_pagos = ws_pagos.row_values(1)
        if "viaje_id" not in header_pagos:
            ws_pagos.update_cell(1, len(header_pagos) + 1, "viaje_id")

    # Hoja de viajes
    try:
        spreadsheet.worksheet("viajes")
    except WorksheetNotFound:
        ws_viajes = spreadsheet.add_worksheet(title="viajes", rows=200, cols=20)
        ws_viajes.append_row(
            [
                "id",
                "nombre",
                "destino",
                "fecha_inicio",
                "fecha_fin",
                "estado",
                "saldado",
                "balance_final",
            ]
        )

    # Hoja de préstamos
    try:
        spreadsheet.worksheet("prestamos")
    except WorksheetNotFound:
        spreadsheet.add_worksheet(title="prestamos", rows=500, cols=15)
        ws_prestamos = spreadsheet.worksheet("prestamos")
        ws_prestamos.append_row(
            [
                "id",
                "fecha",
                "quien_presta",
                "quien_recibe",
                "monto",
                "motivo",
                "estado",
                "monto_abonado",
                "created_at",
            ]
        )

    # Hoja de abonos a préstamos
    try:
        spreadsheet.worksheet("abonos_prestamos")
    except WorksheetNotFound:
        spreadsheet.add_worksheet(title="abonos_prestamos", rows=500, cols=10)
        ws_abonos_p = spreadsheet.worksheet("abonos_prestamos")
        ws_abonos_p.append_row(
            ["id", "prestamo_id", "fecha", "monto", "nota", "created_at"]
        )

    # Hoja de config
    try:
        ws_config = spreadsheet.worksheet("config")
    except WorksheetNotFound:
        ws_config = spreadsheet.add_worksheet(title="config", rows=100, cols=5)
        ws_config.append_row(["key", "value"])
        ws_config.append_row(["persona1", "Persona 1"])
        ws_config.append_row(["persona2", "Persona 2"])
        return

    # Asegurar que existan claves persona1 y persona2
    keys = ws_config.col_values(1)
    if "key" not in keys:
        ws_config.update("A1:B1", [["key", "value"]])
        keys = ["key"]
    if "persona1" not in keys:
        ws_config.append_row(["persona1", "Persona 1"])
    if "persona2" not in keys:
        ws_config.append_row(["persona2", "Persona 2"])


@st.cache_data(ttl=30)
def load_gastos_df() -> pd.DataFrame:
    """Carga todos los gastos como DataFrame."""
    ws = get_worksheet("gastos")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Tipos de datos
    df["id"] = pd.to_numeric(df.get("id", 0), errors="coerce").astype("Int64")
    df["monto"] = pd.to_numeric(df.get("monto", 0.0), errors="coerce").fillna(0.0)
    df["porcentaje_persona1"] = pd.to_numeric(
        df.get("porcentaje_persona1", 50.0), errors="coerce"
    ).fillna(50.0)
    df["porcentaje_persona2"] = pd.to_numeric(
        df.get("porcentaje_persona2", 50.0), errors="coerce"
    ).fillna(50.0)
    # viaje_id puede ser nulo
    if "viaje_id" in df.columns:
        df["viaje_id"] = pd.to_numeric(df.get("viaje_id", None), errors="coerce").astype(
            "Int64"
        )
    else:
        df["viaje_id"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    return df


@st.cache_data(ttl=30)
def load_pagos_df() -> pd.DataFrame:
    """Carga todos los pagos/abonos como DataFrame."""
    ws = get_worksheet("pagos")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df

    df["id"] = pd.to_numeric(df.get("id", 0), errors="coerce").astype("Int64")
    df["monto"] = pd.to_numeric(df.get("monto", 0.0), errors="coerce").fillna(0.0)
    if "viaje_id" in df.columns:
        df["viaje_id"] = pd.to_numeric(df.get("viaje_id", None), errors="coerce").astype(
            "Int64"
        )
    else:
        df["viaje_id"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    if "categoria" not in df.columns:
        df["categoria"] = ""
    return df


@st.cache_data(ttl=30)
def load_viajes_df() -> pd.DataFrame:
    """Carga todos los viajes como DataFrame."""
    ws = get_worksheet("viajes")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df

    df["id"] = pd.to_numeric(df.get("id", 0), errors="coerce").astype("Int64")
    df["balance_final"] = pd.to_numeric(
        df.get("balance_final", 0.0), errors="coerce"
    ).fillna(0.0)
    # Fechas como strings ISO; opcionalmente parseamos a date para usar en UI
    for col in ["fecha_inicio", "fecha_fin"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df


@st.cache_data(ttl=30)
def load_prestamos_df() -> pd.DataFrame:
    """Carga todos los préstamos como DataFrame."""
    ws = get_worksheet("prestamos")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["id"] = pd.to_numeric(df.get("id", 0), errors="coerce").astype("Int64")
    df["monto"] = pd.to_numeric(df.get("monto", 0.0), errors="coerce").fillna(0.0)
    df["monto_abonado"] = pd.to_numeric(
        df.get("monto_abonado", 0.0), errors="coerce"
    ).fillna(0.0)
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    return df


@st.cache_data(ttl=30)
def load_abonos_prestamos_df() -> pd.DataFrame:
    """Carga todos los abonos a préstamos como DataFrame."""
    ws = get_worksheet("abonos_prestamos")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["id"] = pd.to_numeric(df.get("id", 0), errors="coerce").astype("Int64")
    df["prestamo_id"] = pd.to_numeric(
        df.get("prestamo_id", 0), errors="coerce"
    ).astype("Int64")
    df["monto"] = pd.to_numeric(df.get("monto", 0.0), errors="coerce").fillna(0.0)
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    return df


@st.cache_data(ttl=30)
def load_config_dict() -> Dict[str, str]:
    """Carga la configuración como diccionario clave-valor."""
    ws = get_worksheet("config")
    records = ws.get_all_records()
    config = {row["key"]: str(row["value"]) for row in records if "key" in row}
    if "persona1" not in config:
        config["persona1"] = "Persona 1"
    if "persona2" not in config:
        config["persona2"] = "Persona 2"
    return config


def set_config_value(key: str, value: str) -> None:
    """Actualiza/inserta una clave de configuración."""
    ws = get_worksheet("config")
    all_values = ws.get_all_values()
    # Buscar fila por clave en la primera columna
    target_row = None
    for idx, row in enumerate(all_values, start=1):
        if row and row[0] == key:
            target_row = idx
            break
    if target_row is None:
        ws.append_row([key, value])
    else:
        ws.update(f"B{target_row}", [[value]])
    st.cache_data.clear()


def _next_id_for_worksheet(ws) -> int:
    """Calcula el siguiente ID incremental basado en la columna A."""
    all_values = ws.get_all_values()
    if len(all_values) <= 1:
        return 1
    ids = []
    for row in all_values[1:]:
        if not row:
            continue
        try:
            ids.append(int(row[0]))
        except Exception:
            continue
    return max(ids) + 1 if ids else 1


def add_gasto(
    fecha: date,
    descripcion: str,
    monto: float,
    quien_pago: str,
    categoria: str,
    subcategoria: str,
    tipo_division: str,
    pct1: float,
    pct2: float,
    viaje_id=None,
) -> None:
    """Agrega un nuevo gasto."""
    ws = get_worksheet("gastos")
    next_id = _next_id_for_worksheet(ws)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row(
        [
            next_id,
            str(fecha),
            descripcion,
            float(monto),
            quien_pago,
            categoria,
            subcategoria,
            tipo_division,
            float(pct1),
            float(pct2),
            now,
            viaje_id if viaje_id is not None else "",
        ]
    )
    st.cache_data.clear()


def _find_row_index_by_id(ws, record_id: int) -> int:
    """Devuelve el índice de fila (1-based) para un ID dado, o -1 si no existe."""
    all_values = ws.get_all_values()
    for idx, row in enumerate(all_values[1:], start=2):
        if not row:
            continue
        try:
            if int(row[0]) == int(record_id):
                return idx
        except Exception:
            continue
    return -1


def update_gasto(
    record_id: int,
    fecha: date,
    descripcion: str,
    monto: float,
    quien_pago: str,
    categoria: str,
    subcategoria: str,
    tipo_division: str,
    pct1: float,
    pct2: float,
    viaje_id=None,
) -> None:
    """Actualiza un gasto existente por ID."""
    ws = get_worksheet("gastos")
    row_index = _find_row_index_by_id(ws, record_id)
    if row_index == -1:
        st.warning("No se encontró el gasto a actualizar.")
        return
    values = [
        record_id,
        str(fecha),
        descripcion,
        float(monto),
        quien_pago,
        categoria,
        subcategoria,
        tipo_division,
        float(pct1),
        float(pct2),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        viaje_id if viaje_id is not None else "",
    ]
    ws.update(f"A{row_index}:L{row_index}", [values])
    st.cache_data.clear()


def delete_gasto(record_id: int) -> None:
    """Elimina un gasto por ID."""
    ws = get_worksheet("gastos")
    row_index = _find_row_index_by_id(ws, record_id)
    if row_index == -1:
        st.warning("No se encontró el gasto a eliminar.")
        return
    ws.delete_rows(row_index)
    st.cache_data.clear()


def add_pago(
    fecha: date,
    quien_paga: str,
    quien_recibe: str,
    monto: float,
    categoria: str,
    nota: str,
    viaje_id=None,
) -> None:
    """Registra un pago/abono."""
    ws = get_worksheet("pagos")
    next_id = _next_id_for_worksheet(ws)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row(
        [
            next_id,
            str(fecha),
            quien_paga,
            quien_recibe,
            float(monto),
            categoria,
            nota,
            now,
            viaje_id if viaje_id is not None else "",
        ]
    )
    st.cache_data.clear()


def crear_viaje(nombre: str, destino: str, fecha_inicio: date, fecha_fin: date) -> None:
    """Crea un nuevo viaje activo. Solo puede haber uno activo a la vez."""
    ws = get_worksheet("viajes")
    df_viajes = load_viajes_df()
    if not df_viajes.empty and (
        df_viajes.get("estado", "").astype(str).str.lower() == "activo"
    ).any():
        st.error("Ya existe un viaje activo. Debes cerrarlo antes de crear uno nuevo.")
        return

    next_id = _next_id_for_worksheet(ws)
    ws.append_row(
        [
            next_id,
            nombre,
            destino,
            str(fecha_inicio),
            str(fecha_fin),
            "activo",
            "pendiente",
            0.0,
        ]
    )
    st.cache_data.clear()


def cerrar_viaje(viaje_id: int, saldado: bool, balance_final: float) -> None:
    """Cierra un viaje (estado='cerrado') y marca si quedó saldado o pendiente."""
    ws = get_worksheet("viajes")
    row_index = _find_row_index_by_id(ws, viaje_id)
    if row_index == -1:
        st.warning("No se encontró el viaje a cerrar.")
        return

    row_values = ws.row_values(row_index)
    # Aseguramos longitud mínima de 8 columnas
    while len(row_values) < 8:
        row_values.append("")

    row_values[5] = "cerrado"
    row_values[6] = "saldado" if saldado else "pendiente"
    row_values[7] = float(balance_final)

    ws.update(f"A{row_index}:H{row_index}", [row_values[:8]])
    st.cache_data.clear()


def add_prestamo(
    fecha: date,
    quien_presta: str,
    quien_recibe: str,
    monto: float,
    motivo: str,
) -> None:
    """Registra un nuevo préstamo entre la pareja."""
    ws = get_worksheet("prestamos")
    next_id = _next_id_for_worksheet(ws)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row(
        [
            next_id,
            str(fecha),
            quien_presta,
            quien_recibe,
            float(monto),
            motivo or "",
            "activo",
            0.0,
            now,
        ]
    )
    st.cache_data.clear()


def add_abono_prestamo(prestamo_id: int, fecha: date, monto: float, nota: str) -> None:
    """Registra un abono a un préstamo y actualiza monto_abonado y estado del préstamo."""
    ws_abonos = get_worksheet("abonos_prestamos")
    ws_prestamos = get_worksheet("prestamos")
    next_id = _next_id_for_worksheet(ws_abonos)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws_abonos.append_row(
        [next_id, int(prestamo_id), str(fecha), float(monto), nota or "", now]
    )

    row_index = _find_row_index_by_id(ws_prestamos, prestamo_id)
    if row_index == -1:
        st.cache_data.clear()
        return
    row_values = ws_prestamos.row_values(row_index)
    while len(row_values) < 9:
        row_values.append("")
    try:
        monto_total = float(row_values[4])
        monto_abonado_prev = float(row_values[7]) if row_values[7] else 0.0
    except (ValueError, IndexError):
        monto_total = 0.0
        monto_abonado_prev = 0.0
    nuevo_abonado = monto_abonado_prev + float(monto)
    if nuevo_abonado >= monto_total:
        estado = "saldado"
        nuevo_abonado = monto_total
    else:
        estado = "parcial"
    row_values[6] = estado
    row_values[7] = nuevo_abonado
    ws_prestamos.update(
        f"G{row_index}:H{row_index}",
        [[row_values[6], row_values[7]]],
    )
    st.cache_data.clear()


def calcular_balance_prestamos(
    df_prestamos: pd.DataFrame, persona1: str, persona2: str
) -> float:
    """
    Balance de préstamos: positivo = persona2 le debe a persona1.
    Solo considera préstamos activos o parciales (saldo > 0).
    """
    if df_prestamos.empty or "quien_presta" not in df_prestamos.columns:
        return 0.0
    balance = 0.0
    for _, row in df_prestamos.iterrows():
        estado = (row.get("estado") or "").strip().lower()
        if estado == "saldado":
            continue
        monto = float(row.get("monto", 0.0))
        abonado = float(row.get("monto_abonado", 0.0))
        saldo = monto - abonado
        if saldo <= 0:
            continue
        if str(row.get("quien_presta", "")) == persona1:
            balance += saldo
        else:
            balance -= saldo
    return balance


def calcular_balance(
    df_gastos: pd.DataFrame,
    df_pagos: pd.DataFrame,
    persona1: str,
    persona2: str,
) -> Tuple[float, Dict[str, float]]:
    """
    Calcula el balance entre dos personas.
    Retorna: (balance_p1, resumen_dict)
    - balance positivo = persona2 le debe a persona1
    - balance negativo = persona1 le debe a persona2
    """
    corresponde_p1 = 0.0
    corresponde_p2 = 0.0
    pago_p1 = 0.0
    pago_p2 = 0.0

    if not df_gastos.empty:
        for _, row in df_gastos.iterrows():
            monto = float(row.get("monto", 0.0))
            quien = row.get("quien_pago", "")
            division = row.get("tipo_division", "50/50")
            pct1 = float(row.get("porcentaje_persona1", 50.0))
            pct2 = float(row.get("porcentaje_persona2", 50.0))

            if quien == persona1:
                pago_p1 += monto
            elif quien == persona2:
                pago_p2 += monto

            if division == "50/50":
                corresponde_p1 += monto * 0.5
                corresponde_p2 += monto * 0.5
            elif division == "personal":
                if quien == persona1:
                    corresponde_p1 += monto
                elif quien == persona2:
                    corresponde_p2 += monto
            elif division == "custom":
                corresponde_p1 += monto * (pct1 / 100.0)
                corresponde_p2 += monto * (pct2 / 100.0)

    abonos_p1_a_p2 = 0.0
    abonos_p2_a_p1 = 0.0

    if not df_pagos.empty:
        for _, row in df_pagos.iterrows():
            if row.get("quien_paga") == persona1 and row.get("quien_recibe") == persona2:
                abonos_p1_a_p2 += float(row.get("monto", 0.0))
            elif row.get("quien_paga") == persona2 and row.get("quien_recibe") == persona1:
                abonos_p2_a_p1 += float(row.get("monto", 0.0))

    # Balance original (sin considerar abonos) desde la perspectiva de persona1
    balance_sin_abonos = pago_p1 - corresponde_p1
    # Balance final considerando abonos
    balance_p1 = balance_sin_abonos - abonos_p1_a_p2 - abonos_p2_a_p1

    # Cálculo detallado de deuda, abonos y saldo pendiente
    if abs(balance_sin_abonos) < 1:
        deudor = None
        acreedor = None
        deuda_original = 0.0
        abonos_aplicados = 0.0
        saldo_pendiente = 0.0
        porcentaje_pagado = 0.0
    elif balance_sin_abonos > 0:
        # persona2 le debe a persona1
        deudor = persona2
        acreedor = persona1
        deuda_original = balance_sin_abonos
        abonos_aplicados = abonos_p2_a_p1
    else:
        # persona1 le debe a persona2
        deudor = persona1
        acreedor = persona2
        deuda_original = abs(balance_sin_abonos)
        abonos_aplicados = abonos_p1_a_p2

        # saldo y porcentaje pagado
    if abs(balance_sin_abonos) >= 1 and deuda_original > 0:
        saldo_pendiente = max(deuda_original - abonos_aplicados, 0.0)
        porcentaje_pagado = min((abonos_aplicados / deuda_original) * 100.0, 100.0)
    else:
        saldo_pendiente = 0.0
        porcentaje_pagado = 0.0

    return balance_p1, {
        "total_gastado": pago_p1 + pago_p2,
        "pago_p1": pago_p1,
        "pago_p2": pago_p2,
        "corresponde_p1": corresponde_p1,
        "corresponde_p2": corresponde_p2,
        "abonos_p1_a_p2": abonos_p1_a_p2,
        "abonos_p2_a_p1": abonos_p2_a_p1,
        "balance_sin_abonos": balance_sin_abonos,
        "deudor": deudor,
        "acreedor": acreedor,
        "deuda_original": deuda_original,
        "abonos_aplicados": abonos_aplicados,
        "saldo_pendiente": saldo_pendiente,
        "porcentaje_pagado": porcentaje_pagado,
        "balance_p1": balance_p1,
    }


def mostrar_mensaje_balance(balance_p1: float, persona1: str, persona2: str) -> None:
    """Muestra un mensaje grande y colorido con el balance."""
    if abs(balance_p1) < 1:
        mensaje = f"✅ Están a mano, nadie le debe a nadie."
        color = "#0EA5E9"
    elif balance_p1 > 0:
        mensaje = (
            f"💰 {persona2} le debe {formatear_cop(balance_p1)} a {persona1}"
        )
        color = "#059669"
    else:
        mensaje = (
            f"💰 {persona1} le debe {formatear_cop(abs(balance_p1))} a {persona2}"
        )
        color = "#DC2626"

    st.markdown(
        f"<h2 style='text-align:center; color:{color};'>{mensaje}</h2>",
        unsafe_allow_html=True,
    )


def render_estado_cuenta_y_pagos(
    categoria: str,
    persona1: str,
    persona2: str,
    df_gastos_cat: pd.DataFrame,
    df_pagos_cat: pd.DataFrame,
    resumen: Dict[str, Any],
    key_prefix: str,
    viaje_id=None,
) -> None:
    """Muestra el extracto de deuda y el formulario de abonos para una categoría."""
    st.markdown("### 📑 Estado de cuenta")
    deuda_original = float(resumen.get("deuda_original", 0.0) or 0.0)
    porcentaje_pagado = float(resumen.get("porcentaje_pagado", 0.0) or 0.0)
    saldo_pendiente = float(resumen.get("saldo_pendiente", 0.0) or 0.0)
    deudor = resumen.get("deudor")
    acreedor = resumen.get("acreedor")

    st.write(f"**Deuda original:** {formatear_cop(deuda_original)}")
    if not df_pagos_cat.empty and "fecha" in df_pagos_cat.columns and "monto" in df_pagos_cat.columns:
        df_ord = df_pagos_cat.copy()
        df_ord["fecha_dt"] = pd.to_datetime(df_ord["fecha"], errors="coerce")
        df_ord = df_ord.sort_values("fecha_dt")
        for i, (_, r) in enumerate(df_ord.iterrows(), 1):
            f = r.get("fecha", "")
            try:
                f_short = pd.to_datetime(f).strftime("%d %b") if f else ""
            except Exception:
                f_short = str(f)[:10]
            m = formatear_cop(r.get("monto", 0))
            nota = (r.get("nota") or "") if isinstance(r.get("nota"), str) else ""
            st.caption(f"Abono {i} ({f_short}): {m}" + (f" | {nota}" if nota else ""))
    st.write(f"**Total abonado:** {formatear_cop(resumen.get('abonos_aplicados', 0.0))}")
    st.markdown(f"**SALDO PENDIENTE:** <span style='color:#D97706;font-weight:700;'>{formatear_cop(saldo_pendiente)}</span>", unsafe_allow_html=True)

    progreso = porcentaje_pagado / 100.0 if deuda_original > 0 else 0.0
    st.progress(progreso, text=f"{porcentaje_pagado:,.1f}% pagado" if deuda_original > 0 else "Sin deuda")

    # Balance neto real (incluye sobrepagos: si alguien pagó de más, la deuda se invierte)
    balance_p1_actual = float(resumen.get("balance_p1", 0.0) or 0.0)
    if abs(balance_p1_actual) < 1:
        current_deudor = None
        current_monto_neto = 0.0
    elif balance_p1_actual > 0:
        current_deudor = persona2
        current_monto_neto = balance_p1_actual
    else:
        current_deudor = persona1
        current_monto_neto = abs(balance_p1_actual)

    if current_monto_neto < 1:
        st.success("Esta categoría está completamente saldada entre ambas personas.")
    elif saldo_pendiente > 0:
        st.info(
            f"{deudor} aún le debe {formatear_cop(saldo_pendiente)} a {acreedor} "
            f"(abonó {formatear_cop(resumen.get('abonos_aplicados', 0.0))} "
            f"de {formatear_cop(deuda_original)})."
        )
    else:
        st.warning(
            f"La deuda original fue saldada, pero quedó un **sobrepago de {formatear_cop(current_monto_neto)}**. "
            f"**{current_deudor}** debe ese diferencial."
        )

    st.markdown("### 💸 Registrar pago o abono")
    with st.form(f"form_pago_{key_prefix}"):
        fecha_pago = st.date_input(
            "Fecha del pago",
            value=date.today(),
            key=f"fecha_pago_{key_prefix}",
        )

        if current_deudor in (persona1, persona2):
            idx_default = 0 if current_deudor == persona1 else 1
        else:
            idx_default = 0

        quien_paga = st.selectbox(
            "Quién paga",
            [persona1, persona2],
            index=idx_default,
            key=f"quien_paga_{key_prefix}",
        )
        quien_recibe = persona2 if quien_paga == persona1 else persona1
        st.caption(f"Este abono se registrará como pago de {quien_paga} a {quien_recibe}.")

        tipo_pago = st.radio(
            "Tipo de pago",
            ["Pagar todo", "Abonar parcial"],
            index=0,
            key=f"tipo_pago_{key_prefix}",
        )
        monto_input = st.number_input(
            "Monto (COP)",
            min_value=0.0,
            step=1000.0,
            format="%.0f",
            key=f"monto_pago_{key_prefix}",
        )
        metodo_pago = st.selectbox(
            "Método de pago (opcional)",
            ["", "Transferencia", "Nequi", "Daviplata", "Efectivo", "Otro"],
            key=f"metodo_pago_{key_prefix}",
        )
        nota = st.text_input("Nota (opcional)", key=f"nota_pago_{key_prefix}")

        submitted = st.form_submit_button("Registrar pago")
        if submitted:
            if current_monto_neto < 1:
                st.error("No hay saldo pendiente entre ambas personas en esta categoría.")
            else:
                monto = current_monto_neto if tipo_pago == "Pagar todo" else monto_input
                if monto <= 0:
                    st.error("El monto debe ser mayor a cero.")
                else:
                    nota_final = (f"{metodo_pago}: {nota}".strip() if metodo_pago else (nota or "")) or ""
                    add_pago(
                        fecha=fecha_pago,
                        quien_paga=quien_paga,
                        quien_recibe=quien_recibe,
                        monto=monto,
                        categoria=categoria,
                        nota=nota_final,
                        viaje_id=viaje_id,
                    )
                    st.success("Pago registrado correctamente.")
                    st.rerun()

    st.markdown("### 🕒 Historial de pagos")
    deudor = resumen.get("deudor")
    acreedor = resumen.get("acreedor")
    deuda_orig = float(resumen.get("deuda_original", 0.0) or 0.0)
    if deuda_orig > 0 and deudor and acreedor:
        st.caption(f"Se generó deuda de {formatear_cop(deuda_orig)}. {deudor} le debe a {acreedor}.")
    if df_pagos_cat.empty:
        if deuda_orig <= 0:
            st.info("No hay pagos ni deuda en esta categoría.")
        else:
            st.info("Aún no hay pagos registrados para esta categoría.")
    else:
        df_hist = df_pagos_cat.copy()
        if "fecha" in df_hist.columns:
            df_hist["fecha_dt"] = pd.to_datetime(df_hist["fecha"], errors="coerce")
            df_hist = df_hist.sort_values("fecha_dt", ascending=False)
        for _, r in df_hist.iterrows():
            f = r.get("fecha", "")
            try:
                f_str = pd.to_datetime(f).strftime("%d %b %Y") if f else ""
            except Exception:
                f_str = str(f)[:10]
            qp = r.get("quien_paga", "")
            qr = r.get("quien_recibe", "")
            m = formatear_cop(r.get("monto", 0))
            nota = (r.get("nota") or "") if isinstance(r.get("nota"), str) else ""
            st.markdown(f"- **{f_str}:** {qp} abonó {m} a {qr}" + (f" | {nota}" if nota else ""))
        st.markdown("---")
        df_hist_tab = df_hist.copy()
        df_hist_tab["monto"] = df_hist_tab["monto"].apply(formatear_cop)
        df_hist_tab.rename(
            columns={
                "fecha": "Fecha",
                "quien_paga": "Quién paga",
                "quien_recibe": "Quién recibe",
                "monto": "Monto",
                "nota": "Nota",
            },
            inplace=True,
        )
        st.dataframe(
            df_hist_tab[["Fecha", "Quién paga", "Quién recibe", "Monto", "Nota"]],
            use_container_width=True,
        )


def render_resumen_categoria(
    categoria: str,
    persona1: str,
    persona2: str,
    viaje_id=None,
) -> None:
    """Renderiza resumen, tabla y herramientas para una categoría."""
    with st.spinner("Cargando datos..."):
        df_gastos = load_gastos_df()
        df_pagos = load_pagos_df()

    if not df_gastos.empty and "categoria" in df_gastos.columns:
        df_cat = df_gastos[df_gastos["categoria"] == categoria].copy()
    else:
        df_cat = df_gastos.copy()

    if not df_pagos.empty and "categoria" in df_pagos.columns:
        df_pagos_cat = df_pagos[df_pagos["categoria"] == categoria].copy()
    else:
        df_pagos_cat = df_pagos.copy()

    if viaje_id is not None and "viaje_id" in df_cat.columns:
        df_cat = df_cat[df_cat.get("viaje_id") == int(viaje_id)]
    if viaje_id is not None and "viaje_id" in df_pagos_cat.columns:
        df_pagos_cat = df_pagos_cat[df_pagos_cat.get("viaje_id") == int(viaje_id)]

    balance_p1, resumen = calcular_balance(df_cat, df_pagos_cat, persona1, persona2)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total gastado", formatear_cop(resumen["total_gastado"]))
    with col2:
        st.metric(f"Pagado por {persona1}", formatear_cop(resumen["pago_p1"]))
    with col3:
        st.metric(f"Pagado por {persona2}", formatear_cop(resumen["pago_p2"]))

    mostrar_mensaje_balance(balance_p1, persona1, persona2)

    # Extracto y abonos para esta categoría
    render_estado_cuenta_y_pagos(
        categoria=categoria,
        persona1=persona1,
        persona2=persona2,
        df_gastos_cat=df_cat,
        df_pagos_cat=df_pagos_cat,
        resumen=resumen,
        key_prefix=f"{categoria}_{viaje_id if viaje_id is not None else 'general'}",
        viaje_id=viaje_id,
    )

    if df_cat.empty:
        st.info("Aún no hay gastos registrados en esta categoría.")
        return

    # Conversión de fecha
    df_cat["fecha_dt"] = pd.to_datetime(df_cat["fecha"], errors="coerce")
    min_fecha = df_cat["fecha_dt"].min()
    max_fecha = df_cat["fecha_dt"].max()
    if pd.isna(min_fecha) or pd.isna(max_fecha):
        min_fecha = max_fecha = datetime.today()

    st.subheader("📅 Filtros")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        rango_fechas = st.date_input(
            "Rango de fechas",
            (min_fecha.date(), max_fecha.date()),
            key=f"rango_{categoria}",
        )
    with col_f2:
        opciones_quien = sorted(df_cat["quien_pago"].dropna().unique().tolist())
        seleccion_quien = st.multiselect(
            "Quién pagó",
            opciones_quien,
            default=opciones_quien,
            key=f"quien_{categoria}",
        )

    # Aplicar filtros
    if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
        desde, hasta = rango_fechas
    else:
        desde = hasta = rango_fechas
    df_filtrado = df_cat[
        (df_cat["fecha_dt"] >= pd.to_datetime(desde))
        & (df_cat["fecha_dt"] <= pd.to_datetime(hasta))
    ]
    if seleccion_quien:
        df_filtrado = df_filtrado[df_filtrado["quien_pago"].isin(seleccion_quien)]

    st.subheader("📊 Visualizaciones")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        df_pagos_por_persona = (
            df_filtrado.groupby("quien_pago")["monto"].sum().reset_index()
        )
        if not df_pagos_por_persona.empty:
            fig_bar = px.bar(
                df_pagos_por_persona,
                x="quien_pago",
                y="monto",
                labels={"quien_pago": "Persona", "monto": "Monto pagado"},
                title="Comparación de pagos por persona",
                color="quien_pago",
            color_discrete_sequence=["#0EA5E9", "#10B981"],
            )
            fig_bar.update_yaxes(tickprefix="$", separatethousands=True)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No hay datos suficientes para el gráfico de barras.")

    with col_g2:
        df_por_sub = (
            df_filtrado.groupby("subcategoria")["monto"].sum().reset_index()
        )
        if not df_por_sub.empty:
            fig_pie = px.pie(
                df_por_sub,
                names="subcategoria",
                values="monto",
                title="Distribución por subcategoría",
                hole=0.4,
            color_discrete_sequence=["#0EA5E9", "#38BDF8"],
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No hay datos suficientes para el gráfico de subcategorías.")

    st.subheader("📋 Tabla de gastos")
    df_mostrar = df_filtrado[
        ["id", "fecha", "descripcion", "subcategoria", "monto", "quien_pago", "tipo_division"]
    ].copy()
    df_mostrar.rename(
        columns={
            "fecha": "Fecha",
            "descripcion": "Descripción",
            "subcategoria": "Subcategoría",
            "monto": "Monto",
            "quien_pago": "Quién pagó",
            "tipo_division": "División",
        },
        inplace=True,
    )
    df_mostrar["Monto"] = df_mostrar["Monto"].apply(formatear_cop)
    st.dataframe(df_mostrar.drop(columns=["id"]), use_container_width=True)

    # Edición / eliminación
    st.subheader("✏️ Editar o eliminar gastos")
    edit_key = f"edit_gasto_id_{categoria}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = None

    with st.expander("Mostrar herramientas de edición", expanded=False):
        for _, row in df_filtrado.sort_values("fecha_dt", ascending=False).iterrows():
            rid = int(row["id"])
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            with c1:
                st.markdown(
                    f"**{row['fecha']}** - {row['descripcion']} "
                    f"({row['subcategoria']}) - {formatear_cop(row['monto'])}"
                )
            with c2:
                st.markdown(f"Pagó: **{row['quien_pago']}** | División: {row['tipo_division']}")
            with c3:
                if st.button("Editar", key=f"edit_{categoria}_{rid}"):
                    st.session_state[edit_key] = rid
            with c4:
                if st.button(
                    "🗑️", key=f"del_{categoria}_{rid}", help="Eliminar gasto definitivamente"
                ):
                    delete_gasto(rid)
                    st.success("Gasto eliminado correctamente.")
                    st.rerun()

        if st.session_state[edit_key] is not None:
            rid = st.session_state[edit_key]
            registro = df_cat[df_cat["id"] == rid]
            if registro.empty:
                st.warning("No se encontró el gasto a editar.")
            else:
                row = registro.iloc[0]
                st.markdown("---")
                st.markdown(f"### Editar gasto #{rid}")
                with st.form(key=f"form_edit_{categoria}"):
                    fecha_edit = st.date_input(
                        "Fecha",
                        value=pd.to_datetime(row["fecha"]).date()
                        if pd.notna(row["fecha"])
                        else date.today(),
                    )
                    desc_edit = st.text_input("Descripción", value=row["descripcion"])
                    monto_edit = st.number_input(
                        "Monto (COP)",
                        min_value=0.0,
                        value=float(row["monto"]),
                        step=1000.0,
                        format="%.0f",
                    )
                    quien_edit = st.selectbox(
                        "Quién pagó",
                        [persona1, persona2],
                        index=0 if row["quien_pago"] == persona1 else 1,
                    )
                    subcat_opciones = (
                        [
                            "Transporte",
                            "Hospedaje",
                            "Alimentación",
                            "Entretenimiento",
                            "Compras",
                            "Otros",
                        ]
                        if categoria == "viaje"
                        else [
                            "Mercado",
                            "Servicios Públicos",
                            "Arriendo/Hipoteca",
                            "Internet/TV",
                            "Salud",
                            "Transporte",
                            "Restaurantes",
                            "Otros",
                        ]
                    )
                    subcat_edit = st.selectbox(
                        "Subcategoría",
                        subcat_opciones,
                        index=subcat_opciones.index(row["subcategoria"])
                        if row["subcategoria"] in subcat_opciones
                        else len(subcat_opciones) - 1,
                    )

                    tipo_div_edit = st.radio(
                        "División",
                        ["50/50", "personal", "custom"],
                        index=["50/50", "personal", "custom"].index(
                            row.get("tipo_division", "50/50")
                        ),
                    )
                    pct1_edit = row.get("porcentaje_persona1", 50.0)
                    if tipo_div_edit == "custom":
                        pct1_edit = st.slider(
                            f"Porcentaje para {persona1}",
                            min_value=0,
                            max_value=100,
                            value=int(pct1_edit),
                        )
                    else:
                        pct1_edit = 50 if tipo_div_edit == "50/50" else (
                            100 if quien_edit == persona1 else 0
                        )
                    pct2_edit = 100 - pct1_edit

                    submitted_edit = st.form_submit_button("Guardar cambios")
                    if submitted_edit:
                        update_gasto(
                            record_id=rid,
                            fecha=fecha_edit,
                            descripcion=desc_edit,
                            monto=monto_edit,
                            quien_pago=quien_edit,
                            categoria=categoria,
                            subcategoria=subcat_edit,
                            tipo_division=tipo_div_edit,
                            pct1=pct1_edit,
                            pct2=pct2_edit,
                            viaje_id=row.get("viaje_id", None),
                        )
                        st.session_state[edit_key] = None
                        st.success("Gasto actualizado correctamente.")
                        st.rerun()


def render_form_gasto(categoria: str, persona1: str, persona2: str, viaje_id=None) -> None:
    """Formulario para registrar un nuevo gasto."""
    st.subheader("➕ Registrar nuevo gasto")
    with st.form(key=f"form_nuevo_{categoria}"):
        fecha = st.date_input("Fecha del gasto", value=date.today())
        descripcion = st.text_input("Descripción")
        monto = st.number_input(
            "Monto (COP)",
            min_value=0.0,
            step=1000.0,
            format="%.0f",
        )
        quien_pago = st.selectbox("Quién pagó", [persona1, persona2])

        if categoria == "viaje":
            subcat_opciones = [
                "Transporte",
                "Hospedaje",
                "Alimentación",
                "Entretenimiento",
                "Compras",
                "Otros",
            ]
        else:
            subcat_opciones = [
                "Mercado",
                "Servicios Públicos",
                "Arriendo/Hipoteca",
                "Internet/TV",
                "Salud",
                "Transporte",
                "Restaurantes",
                "Otros",
            ]
        subcategoria = st.selectbox("Subcategoría", subcat_opciones)

        tipo_division = st.radio(
            "Cómo se divide el gasto",
            ["50/50", "100% de quien pagó (personal)", "Porcentaje personalizado"],
            index=0,
        )

        # Slider siempre visible para que sea más claro,
        # aunque solo se use cuando se elige "Porcentaje personalizado".
        pct1_slider = st.slider(
            f"Porcentaje para {persona1}",
            min_value=0,
            max_value=100,
            value=50,
        )

        if tipo_division == "50/50":
            tipo_division_val = "50/50"
            pct1 = 50
            pct2 = 50
        elif tipo_division.startswith("100%"):
            tipo_division_val = "personal"
            pct1 = 100 if quien_pago == persona1 else 0
            pct2 = 0 if quien_pago == persona1 else 100
        else:
            tipo_division_val = "custom"
            pct1 = pct1_slider
            pct2 = 100 - pct1
        st.caption(f"A {persona2} le corresponde el {pct2}%")

        submitted = st.form_submit_button("Guardar gasto")
        if submitted:
            if not descripcion or monto <= 0:
                st.error("Por favor ingresa una descripción y un monto mayor a cero.")
            else:
                add_gasto(
                    fecha=fecha,
                    descripcion=descripcion,
                    monto=monto,
                    quien_pago=quien_pago,
                    categoria=categoria,
                    subcategoria=subcategoria,
                    tipo_division=tipo_division_val,
                    pct1=pct1,
                    pct2=pct2,
                    viaje_id=viaje_id,
                )
                st.success("Gasto registrado correctamente.")


def render_pagos_section(persona1: str, persona2: str) -> None:
    """Sección global para registrar pagos/abonos por sección (general, viaje, hogar o préstamos)."""
    st.subheader("💸 Pagos / Abonos entre personas")
    st.caption("Elige a qué sección aplica el abono; el monto se descontará solo de esa sección.")

    # Selector de sección fuera del form para poder mostrar u ocultar el selector de préstamo
    categoria_pago = st.selectbox(
        "Aplica a la categoría",
        ["general", "viaje", "hogar", "prestamos"],
        format_func=lambda x: {
            "general": "General",
            "viaje": "Viaje",
            "hogar": "Hogar",
            "prestamos": "🏦 Préstamos",
        }[x],
        index=0,
        key="pagos_aplica_categoria",
    )

    col1, col2 = st.columns(2)
    with col1:
        with st.form("form_pagos"):
            fecha = st.date_input("Fecha del pago", value=date.today())
            quien_paga = st.selectbox("Quién paga", [persona1, persona2], key="pagos_quien_paga")
            quien_recibe = persona2 if quien_paga == persona1 else persona1
            monto = st.number_input(
                "Monto (COP)",
                min_value=0.0,
                step=1000.0,
                format="%.0f",
                key="pagos_monto",
            )

            prestamo_id_seleccionado = None
            if categoria_pago == "prestamos":
                df_prestamos = load_prestamos_df()
                activos = (
                    df_prestamos[
                        df_prestamos["estado"].astype(str).str.lower().isin(["activo", "parcial"])
                    ].copy()
                    if not df_prestamos.empty and "estado" in df_prestamos.columns
                    else pd.DataFrame()
                )
                if activos.empty:
                    st.warning("No hay préstamos activos. Crea uno en la pestaña 🏦 Préstamos.")
                else:
                    opciones = []
                    for _, r in activos.iterrows():
                        pid = int(r.get("id", 0))
                        motivo = str(r.get("motivo", "")) or f"Préstamo #{pid}"
                        saldo = float(r.get("monto", 0)) - float(r.get("monto_abonado", 0))
                        if saldo > 0:
                            opciones.append((pid, f"#{pid} — {motivo} (saldo {formatear_cop(saldo)})"))
                    if opciones:
                        ids = [o[0] for o in opciones]
                        prestamo_id_seleccionado = st.selectbox(
                            "¿A qué préstamo aplica este abono?",
                            options=ids,
                            format_func=lambda i: next(s for pid, s in opciones if pid == i),
                            key="pagos_prestamo_id",
                        )

            nota = st.text_input("Nota (opcional)", key="pagos_nota")
            submitted_pago = st.form_submit_button("Registrar pago")

            if submitted_pago:
                if monto <= 0:
                    st.error("El monto debe ser mayor a cero.")
                elif categoria_pago == "prestamos":
                    if prestamo_id_seleccionado is None:
                        st.error("Elige un préstamo activo o crea uno en la pestaña Préstamos.")
                    else:
                        add_abono_prestamo(
                            prestamo_id=prestamo_id_seleccionado,
                            fecha=fecha,
                            monto=monto,
                            nota=nota or "",
                        )
                        st.success("Abono registrado en la sección Préstamos. Se descontó de ese préstamo.")
                        st.rerun()
                else:
                    add_pago(
                        fecha=fecha,
                        quien_paga=quien_paga,
                        quien_recibe=quien_recibe,
                        monto=monto,
                        categoria=categoria_pago,
                        nota=nota,
                        viaje_id=None,
                    )
                    st.success("Pago registrado correctamente. Se descontó de la sección elegida.")

    with col2:
        with st.spinner("Cargando historial de pagos..."):
            df_pagos = load_pagos_df()
        if df_pagos.empty:
            st.info("Aún no hay pagos registrados en gastos (viaje/hogar/general).")
        else:
            df_pagos_mostrar = df_pagos.copy()
            df_pagos_mostrar["monto"] = df_pagos_mostrar["monto"].apply(formatear_cop)
            df_pagos_mostrar.rename(
                columns={
                    "fecha": "Fecha",
                    "quien_paga": "Quién paga",
                    "quien_recibe": "Quién recibe",
                    "monto": "Monto",
                    "categoria": "Categoría",
                    "nota": "Nota",
                },
                inplace=True,
            )
            st.markdown("**Historial de abonos (gastos)**")
            st.dataframe(
                df_pagos_mostrar[["Fecha", "Quién paga", "Quién recibe", "Monto", "Categoría", "Nota"]],
                use_container_width=True,
            )
        st.caption("Los abonos a préstamos aparecen en la pestaña 🏦 Préstamos.")


def generar_reporte_texto(
    persona1: str,
    persona2: str,
    df_gastos: pd.DataFrame,
    df_pagos: pd.DataFrame,
) -> str:
    """Genera un resumen en texto plano del estado de cuentas."""
    if not df_gastos.empty and "categoria" in df_gastos.columns:
        df_viaje = df_gastos[df_gastos["categoria"] == "viaje"]
        df_hogar = df_gastos[df_gastos["categoria"] == "hogar"]
    else:
        df_viaje = df_gastos.copy()
        df_hogar = df_gastos.copy()

    if not df_pagos.empty and "categoria" in df_pagos.columns:
        df_pagos_viaje = df_pagos[df_pagos["categoria"] == "viaje"]
        df_pagos_hogar = df_pagos[df_pagos["categoria"] == "hogar"]
    else:
        df_pagos_viaje = df_pagos.copy()
        df_pagos_hogar = df_pagos.copy()

    bal_viaje, res_viaje = calcular_balance(df_viaje, df_pagos_viaje, persona1, persona2)
    bal_hogar, res_hogar = calcular_balance(df_hogar, df_pagos_hogar, persona1, persona2)
    # Global: todos los gastos y todos los pagos (incluye "general")
    bal_global, res_global = calcular_balance(df_gastos, df_pagos, persona1, persona2)

    def resumen_linea(nombre: str, bal: float) -> str:
        if abs(bal) < 1:
            return f"{nombre}: Están a mano."
        if bal > 0:
            return f"{nombre}: {persona2} le debe {formatear_cop(bal)} a {persona1}."
        return f"{nombre}: {persona1} le debe {formatear_cop(abs(bal))} a {persona2}."

    lineas = [
        "REPORTE DE GASTOS COMPARTIDOS",
        f"Personas: {persona1} y {persona2}",
        "",
        "=== Viaje ===",
        f"Total gastado: {formatear_cop(res_viaje['total_gastado'])}",
        f"Pagó {persona1}: {formatear_cop(res_viaje['pago_p1'])}",
        f"Pagó {persona2}: {formatear_cop(res_viaje['pago_p2'])}",
        resumen_linea("Viaje", bal_viaje),
        "",
        "=== Hogar ===",
        f"Total gastado: {formatear_cop(res_hogar['total_gastado'])}",
        f"Pagó {persona1}: {formatear_cop(res_hogar['pago_p1'])}",
        f"Pagó {persona2}: {formatear_cop(res_hogar['pago_p2'])}",
        resumen_linea("Hogar", bal_hogar),
        "",
        "=== Global ===",
        f"Total gastado: {formatear_cop(res_global['total_gastado'])}",
        f"Pagó {persona1}: {formatear_cop(res_global['pago_p1'])}",
        f"Pagó {persona2}: {formatear_cop(res_global['pago_p2'])}",
        resumen_linea("Global", bal_global),
    ]
    return "\n".join(lineas)


def render_prestamos_tab(persona1: str, persona2: str) -> None:
    """Pestaña de préstamos entre la pareja."""
    with st.spinner("Cargando préstamos..."):
        df_prestamos = load_prestamos_df()
        df_abonos = load_abonos_prestamos_df()

    # ----- Sección 1: Registrar nuevo préstamo -----
    st.subheader("🏦 Registrar nuevo préstamo")
    with st.container():
        with st.form("form_nuevo_prestamo"):
            c1, c2 = st.columns(2)
            with c1:
                fecha_prestamo = st.date_input("Fecha del préstamo", value=date.today())
                quien_presta = st.selectbox(
                    "¿Quién presta?",
                    options=[persona1, persona2],
                    key="prestamo_quien_presta",
                )
            quien_recibe = persona2 if quien_presta == persona1 else persona1
            st.caption(f"→ le presta a **{quien_recibe}**")
            monto_prestamo = st.number_input(
                "Monto ($)",
                min_value=1.0,
                value=100000.0,
                step=10000.0,
                format="%.0f",
            )
            motivo_prestamo = st.text_input(
                "Motivo",
                placeholder="Ej: Compra celular, Emergencia médica, Cuota carro",
            )
            if st.form_submit_button("🏦 Registrar préstamo"):
                if not motivo_prestamo.strip():
                    st.error("Indica el motivo del préstamo.")
                else:
                    add_prestamo(
                        fecha=fecha_prestamo,
                        quien_presta=quien_presta,
                        quien_recibe=quien_recibe,
                        monto=monto_prestamo,
                        motivo=motivo_prestamo.strip(),
                    )
                    st.success("Préstamo registrado.")
                    st.rerun()

    st.markdown("---")
    # ----- Sección 2: Préstamos activos -----
    st.subheader("🏦 Préstamos activos")
    activos = pd.DataFrame()
    if not df_prestamos.empty and "estado" in df_prestamos.columns:
        activos = df_prestamos[
            df_prestamos["estado"].astype(str).str.lower().isin(["activo", "parcial"])
        ].copy()
    if activos.empty:
        st.info("No hay préstamos activos o parcialmente pagados.")
    else:
        for _, p in activos.iterrows():
            pid = int(p.get("id", 0))
            monto = float(p.get("monto", 0.0))
            abonado = float(p.get("monto_abonado", 0.0))
            saldo = monto - abonado
            motivo = str(p.get("motivo", "")) or f"Préstamo #{pid}"
            quien_p = str(p.get("quien_presta", ""))
            quien_r = str(p.get("quien_recibe", ""))
            f = p.get("fecha")
            f_str = f.strftime("%d %b %Y") if hasattr(f, "strftime") else str(f)
            pct = (abonado / monto * 100.0) if monto > 0 else 0.0

            with st.expander(
                f"🏦 Préstamo #{pid} — {motivo} · Saldo: {formatear_cop(saldo)}",
                expanded=True,
            ):
                st.markdown(
                    f"**{quien_p}** le prestó **{formatear_cop(monto)}** a **{quien_r}** · {f_str}"
                )
                st.markdown(
                    f"Monto original: **{formatear_cop(monto)}** · "
                    f"Total abonado: **{formatear_cop(abonado)}** · "
                    f"Saldo pendiente: **{formatear_cop(saldo)}**"
                )
                st.progress(min(pct / 100.0, 1.0), text=f"{pct:.1f}% pagado")

                # Formulario de abono inline
                with st.form(key=f"abono_prestamo_{pid}"):
                    tipo_abono = st.radio(
                        "Tipo de abono",
                        options=["pagar_todo", "parcial"],
                        format_func=lambda x: (
                            f"💰 Pagar todo ({formatear_cop(saldo)})"
                            if x == "pagar_todo"
                            else "💳 Abonar parcial"
                        ),
                        key=f"tipo_abono_{pid}",
                    )
                    col_a1, col_a2 = st.columns(2)
                    with col_a1:
                        monto_abono = st.number_input(
                            "Monto a abonar",
                            min_value=0.0,
                            value=saldo if tipo_abono == "pagar_todo" else min(saldo, 100000.0),
                            max_value=saldo,
                            step=10000.0,
                            format="%.0f",
                            key=f"monto_abono_{pid}",
                        )
                        fecha_abono = st.date_input(
                            "Fecha del abono",
                            value=date.today(),
                            key=f"fecha_abono_{pid}",
                        )
                    nota_abono = st.text_input(
                        "Nota (ej: Transferencia Nequi)",
                        key=f"nota_abono_{pid}",
                    )
                    if st.form_submit_button("✅ Registrar abono"):
                        if monto_abono <= 0:
                            st.warning("El monto debe ser mayor a 0.")
                        elif monto_abono > saldo:
                            st.warning("El monto no puede superar el saldo pendiente.")
                        else:
                            add_abono_prestamo(
                                prestamo_id=pid,
                                fecha=fecha_abono,
                                monto=monto_abono,
                                nota=nota_abono or "",
                            )
                            st.success("Abono registrado.")
                            st.rerun()

                # Historial de abonos (timeline)
                st.markdown("**Historial de abonos**")
                abonos_este = (
                    df_abonos[df_abonos["prestamo_id"] == pid].sort_values(
                        "fecha", ascending=False
                    )
                    if not df_abonos.empty and "prestamo_id" in df_abonos.columns
                    else pd.DataFrame()
                )
                if abonos_este.empty:
                    st.caption(f"○ {f_str} — Préstamo creado — {formatear_cop(monto)}")
                else:
                    for _, ab in abonos_este.iterrows():
                        fa = ab.get("fecha")
                        fa_str = fa.strftime("%d %b") if hasattr(fa, "strftime") else str(fa)
                        st.caption(
                            f"● {fa_str} — Abonó {formatear_cop(float(ab.get('monto', 0)))} — "
                            f"\"{ab.get('nota', '')}\""
                        )
                    st.caption(f"○ {f_str} — Préstamo creado — {formatear_cop(monto)}")

    st.markdown("---")
    # ----- Sección 3: Resumen de préstamos -----
    st.subheader("Resumen de préstamos")
    total_prestado = 0.0
    p1_presto = 0.0
    p2_presto = 0.0
    if not df_prestamos.empty:
        total_prestado = float(df_prestamos["monto"].sum())
        if "quien_presta" in df_prestamos.columns:
            for _, r in df_prestamos.iterrows():
                m = float(r.get("monto", 0.0))
                if str(r.get("quien_presta", "")) == persona1:
                    p1_presto += m
                else:
                    p2_presto += m
    balance_p = calcular_balance_prestamos(df_prestamos, persona1, persona2)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🏦 Total Prestado", formatear_cop(total_prestado))
    with col2:
        st.metric(f"💰 {persona1} ha prestado", formatear_cop(p1_presto))
    with col3:
        st.metric(f"💰 {persona2} ha prestado", formatear_cop(p2_presto))
    with col4:
        st.metric("⚖️ Balance Préstamos", formatear_cop(abs(balance_p)))

    if abs(balance_p) < 1:
        st.success("✅ No hay préstamos pendientes.")
    else:
        if balance_p > 0:
            st.info(f"💰 {persona2} le debe {formatear_cop(balance_p)} a {persona1} en préstamos.")
        else:
            st.info(f"💰 {persona1} le debe {formatear_cop(abs(balance_p))} a {persona2} en préstamos.")

    st.markdown("---")
    # ----- Sección 4: Historial de préstamos saldados -----
    st.subheader("Historial de préstamos saldados")
    saldados = pd.DataFrame()
    if not df_prestamos.empty and "estado" in df_prestamos.columns:
        saldados = df_prestamos[
            df_prestamos["estado"].astype(str).str.lower() == "saldado"
        ].copy()
    if saldados.empty:
        st.caption("Aún no hay préstamos saldados.")
    else:
        with st.expander("Ver tabla de préstamos saldados", expanded=False):
            filas = []
            for _, row in saldados.iterrows():
                f_creado = row.get("fecha")
                f_creado_str = (
                    f_creado.strftime("%d %b %Y")
                    if hasattr(f_creado, "strftime")
                    else str(f_creado)
                )
                quien_p = str(row.get("quien_presta", ""))
                quien_r = str(row.get("quien_recibe", ""))
                m = float(row.get("monto", 0.0))
                # Fecha saldado: último abono de este préstamo
                pid = int(row.get("id", 0))
                abonos_p = (
                    df_abonos[df_abonos["prestamo_id"] == pid]
                    if not df_abonos.empty and "prestamo_id" in df_abonos.columns
                    else pd.DataFrame()
                )
                if abonos_p.empty:
                    f_saldado_str = "—"
                    dias_str = "—"
                else:
                    f_saldado = abonos_p["fecha"].max()
                    f_saldado_str = (
                        f_saldado.strftime("%d %b %Y")
                        if hasattr(f_saldado, "strftime")
                        else str(f_saldado)
                    )
                    try:
                        d1 = pd.Timestamp(f_creado) if f_creado else None
                        d2 = pd.Timestamp(f_saldado) if hasattr(f_saldado, "strftime") else f_saldado
                        if d1 is not None and d2 is not None:
                            dias = (d2 - d1).days
                            dias_str = f"{dias} días"
                        else:
                            dias_str = "—"
                    except Exception:
                        dias_str = "—"
                filas.append({
                    "Fecha": f_creado_str,
                    "Préstamo": str(row.get("motivo", "")) or f"#{pid}",
                    "Quién prestó": f"{quien_p} → {quien_r}",
                    "Monto": formatear_cop(m),
                    "Saldado el": f_saldado_str,
                    "Tiempo": dias_str,
                })
            if filas:
                st.dataframe(pd.DataFrame(filas), use_container_width=True)


def render_resumen_global(persona1: str, persona2: str) -> None:
    """Tab de resumen global combinando ambas categorías y préstamos."""
    with st.spinner("Cargando datos globales..."):
        df_gastos = load_gastos_df()
        df_pagos = load_pagos_df()
        df_viajes = load_viajes_df()
        df_prestamos = load_prestamos_df()

    if not df_gastos.empty and "categoria" in df_gastos.columns:
        df_viaje = df_gastos[df_gastos["categoria"] == "viaje"].copy()
        df_hogar = df_gastos[df_gastos["categoria"] == "hogar"].copy()
    else:
        df_viaje = df_gastos.copy()
        df_hogar = df_gastos.copy()

    if not df_pagos.empty and "categoria" in df_pagos.columns:
        df_pagos_viaje = df_pagos[df_pagos["categoria"] == "viaje"].copy()
        df_pagos_hogar = df_pagos[df_pagos["categoria"] == "hogar"].copy()
    else:
        df_pagos_viaje = df_pagos.copy()
        df_pagos_hogar = df_pagos.copy()

    bal_viaje, res_viaje = calcular_balance(df_viaje, df_pagos_viaje, persona1, persona2)
    bal_hogar, res_hogar = calcular_balance(df_hogar, df_pagos_hogar, persona1, persona2)
    bal_prestamos = calcular_balance_prestamos(df_prestamos, persona1, persona2)
    bal_global, res_global = calcular_balance(df_gastos, df_pagos, persona1, persona2)

    # Colores claros por sección (fondo + borde). Los abonos restan en su propia sección.
    VIAJE_BG, VIAJE_BORDER = "#E0F2FE", "#0EA5E9"
    HOGAR_BG, HOGAR_BORDER = "#D1FAE5", "#10B981"
    PRESTAMOS_BG, PRESTAMOS_BORDER = "#FEF3C7", "#D97706"
    SALDO_POS = "#059669"
    SALDO_NEG = "#DC2626"

    def _saldo_color(val: float) -> str:
        return SALDO_POS if val >= 0 else SALDO_NEG

    # ----- Tres secciones separadas: cada una con su saldo (no se mezclan las deudas) -----
    st.markdown("**Los valores se muestran por sección. Cada abono se resta solo en su sección (viaje, hogar o préstamo).**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f'<div style="background:{VIAJE_BG};border-radius:12px;padding:1rem;border:2px solid {VIAJE_BORDER};margin-bottom:0.5rem;">'
            f'<span style="font-size:1.2rem;">🧳</span> <strong>Viaje</strong><br>'
            f'<span style="color:{_saldo_color(bal_viaje)};font-size:1.1rem;">Saldo: {formatear_cop(abs(bal_viaje))}</span><br>'
            f'<small style="color:#64748B;">Abonos restan aquí</small></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div style="background:{HOGAR_BG};border-radius:12px;padding:1rem;border:2px solid {HOGAR_BORDER};margin-bottom:0.5rem;">'
            f'<span style="font-size:1.2rem;">🏠</span> <strong>Hogar</strong><br>'
            f'<span style="color:{_saldo_color(bal_hogar)};font-size:1.1rem;">Saldo: {formatear_cop(abs(bal_hogar))}</span><br>'
            f'<small style="color:#64748B;">Abonos restan aquí</small></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div style="background:{PRESTAMOS_BG};border-radius:12px;padding:1rem;border:2px solid {PRESTAMOS_BORDER};margin-bottom:0.5rem;">'
            f'<span style="font-size:1.2rem;">🏦</span> <strong>Préstamos</strong><br>'
            f'<span style="color:{_saldo_color(bal_prestamos)};font-size:1.1rem;">Saldo: {formatear_cop(abs(bal_prestamos))}</span><br>'
            f'<small style="color:#64748B;">Abonos restan aquí</small></div>',
            unsafe_allow_html=True,
        )

    # ----- Resumen por sección (sin mezclar): mensaje por cada una -----
    st.markdown("---")
    st.markdown(
        '<p style="font-size:1.2rem;color:#475569;font-weight:600;">Resumen por sección</p>',
        unsafe_allow_html=True,
    )
    if abs(bal_viaje) < 1:
        msg_viaje = f"🧳 Viaje: nadie le debe a nadie."
    elif bal_viaje > 0:
        msg_viaje = f"🧳 Viaje: {persona2} le debe {formatear_cop(bal_viaje)} a {persona1}."
    else:
        msg_viaje = f"🧳 Viaje: {persona1} le debe {formatear_cop(abs(bal_viaje))} a {persona2}."
    if abs(bal_hogar) < 1:
        msg_hogar = f"🏠 Hogar: nadie le debe a nadie."
    elif bal_hogar > 0:
        msg_hogar = f"🏠 Hogar: {persona2} le debe {formatear_cop(bal_hogar)} a {persona1}."
    else:
        msg_hogar = f"🏠 Hogar: {persona1} le debe {formatear_cop(abs(bal_hogar))} a {persona2}."
    if abs(bal_prestamos) < 1:
        msg_prestamos = f"🏦 Préstamos: no hay saldo pendiente."
    elif bal_prestamos > 0:
        msg_prestamos = f"🏦 Préstamos: {persona2} le debe {formatear_cop(bal_prestamos)} a {persona1}."
    else:
        msg_prestamos = f"🏦 Préstamos: {persona1} le debe {formatear_cop(abs(bal_prestamos))} a {persona2}."

    st.markdown(f"**{msg_viaje}**")
    st.markdown(f"**{msg_hogar}**")
    st.markdown(f"**{msg_prestamos}**")

    abonado_total = (res_global.get("abonos_p1_a_p2", 0.0) or 0.0) + (
        res_global.get("abonos_p2_a_p1", 0.0) or 0.0
    )
    st.caption(
        f"Abonado en Viaje: {formatear_cop(res_viaje.get('abonos_aplicados') or 0)} · "
        f"Abonado en Hogar: {formatear_cop(res_hogar.get('abonos_aplicados') or 0)}. "
        f"Préstamos: abonos en pestaña Préstamos."
    )

    abonado_total = (res_global.get("abonos_p1_a_p2", 0.0) or 0.0) + (
        res_global.get("abonos_p2_a_p1", 0.0) or 0.0
    )
    # Tres columnas: cada sección con su deuda y abonado (abonos restan en esa sección)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**🧳 Viaje** *(abonos restan aquí)*")
        st.write(f"Debe: {formatear_cop(res_viaje.get('deuda_original') or 0)}")
        st.write(f"Abonado en viaje: {formatear_cop(res_viaje.get('abonos_aplicados') or 0)}")
        st.markdown(f"**Saldo:** <span style='color:{_saldo_color(bal_viaje)}'>{formatear_cop(abs(bal_viaje))}</span>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"**🏠 Hogar** *(abonos restan aquí)*")
        st.write(f"Debe: {formatear_cop(res_hogar.get('deuda_original') or 0)}")
        st.write(f"Abonado en hogar: {formatear_cop(res_hogar.get('abonos_aplicados') or 0)}")
        st.markdown(f"**Saldo:** <span style='color:{_saldo_color(bal_hogar)}'>{formatear_cop(abs(bal_hogar))}</span>", unsafe_allow_html=True)
    with c3:
        st.markdown("**📋 Resumen abonado (gastos)**")
        st.write(formatear_cop(abonado_total))
        st.caption("Suma de abonos en Viaje + Hogar")

    # Barra de progreso global (% de deuda pagada)
    deuda_total_global = float(res_global.get("deuda_original", 0.0) or 0.0)
    abonado_total_global = float(res_global.get("abonos_aplicados", 0.0) or 0.0)
    if deuda_total_global > 0:
        pct_pagado = abonado_total_global / deuda_total_global * 100.0
    else:
        pct_pagado = 100.0 if abs(bal_global) < 1 else 0.0
    st.progress(min(pct_pagado / 100.0, 1.0), text=f"{pct_pagado:.0f}% de deuda total pagada")

    # ----- Préstamos pendientes -----
    st.markdown("### 🏦 Préstamos pendientes")
    st.caption("Los abonos a préstamos se registran en la pestaña Préstamos y restan solo del préstamo correspondiente.")
    activos_p = pd.DataFrame()
    if not df_prestamos.empty and "estado" in df_prestamos.columns:
        activos_p = df_prestamos[
            df_prestamos["estado"].astype(str).str.lower().isin(["activo", "parcial"])
        ].copy()
    if activos_p.empty:
        st.caption("No hay préstamos activos.")
        total_adeudado_prestamos = 0.0
        total_prestado_activo = 0.0
        total_abonado_activo = 0.0
    else:
        total_adeudado_prestamos = 0.0
        total_prestado_activo = float(activos_p["monto"].sum())
        total_abonado_activo = float(activos_p["monto_abonado"].sum())
        total_adeudado_prestamos = total_prestado_activo - total_abonado_activo
        for _, p in activos_p.iterrows():
            m = float(p.get("monto", 0.0))
            ab = float(p.get("monto_abonado", 0.0))
            saldo_p = m - ab
            motivo_p = str(p.get("motivo", "")) or f"Préstamo #{int(p.get('id', 0))}"
            st.caption(f"• {motivo_p}: saldo {formatear_cop(saldo_p)}")
        st.markdown(f"**Total adeudado por préstamos:** {formatear_cop(total_adeudado_prestamos)}")
        if total_prestado_activo > 0:
            pct_prestamos = total_abonado_activo / total_prestado_activo * 100.0
            st.progress(min(pct_prestamos / 100.0, 1.0), text=f"{pct_prestamos:.1f}% de préstamos pagado")

    st.markdown("### Resumen por categoría")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown(
            f'<div style="background:{VIAJE_BG};border-radius:12px;padding:1rem;border:2px solid {VIAJE_BORDER};margin-bottom:1rem;">'
            f'<strong>🧳 Resumen Viaje</strong><br>'
            f'Total gastado: {formatear_cop(res_viaje.get("total_gastado") or 0)}<br>'
            f'{persona1} pagó: {formatear_cop(res_viaje.get("pago_p1") or 0)} · {persona2} pagó: {formatear_cop(res_viaje.get("pago_p2") or 0)}<br>'
            f'Abonado en esta sección: {formatear_cop(res_viaje.get("abonos_aplicados") or 0)}<br>'
            f'<strong>Saldo pendiente:</strong> <span style="color:{_saldo_color(bal_viaje)}">{formatear_cop(abs(bal_viaje))}</span></div>',
            unsafe_allow_html=True,
        )
    with r2:
        st.markdown(
            f'<div style="background:{HOGAR_BG};border-radius:12px;padding:1rem;border:2px solid {HOGAR_BORDER};margin-bottom:1rem;">'
            f'<strong>🏠 Resumen Hogar</strong><br>'
            f'Total gastado: {formatear_cop(res_hogar.get("total_gastado") or 0)}<br>'
            f'{persona1} pagó: {formatear_cop(res_hogar.get("pago_p1") or 0)} · {persona2} pagó: {formatear_cop(res_hogar.get("pago_p2") or 0)}<br>'
            f'Abonado en esta sección: {formatear_cop(res_hogar.get("abonos_aplicados") or 0)}<br>'
            f'<strong>Saldo pendiente:</strong> <span style="color:{_saldo_color(bal_hogar)}">{formatear_cop(abs(bal_hogar))}</span></div>',
            unsafe_allow_html=True,
        )

    # Comparación de gastos por categoría (gráfico de barras)
    st.markdown("### Comparación de gastos por categoría")
    comp_data = []
    if not df_viaje.empty:
        comp_data.append({"Categoría": "Viaje", "Persona": persona1, "Monto": res_viaje.get("pago_p1") or 0})
        comp_data.append({"Categoría": "Viaje", "Persona": persona2, "Monto": res_viaje.get("pago_p2") or 0})
    if not df_hogar.empty:
        comp_data.append({"Categoría": "Hogar", "Persona": persona1, "Monto": res_hogar.get("pago_p1") or 0})
        comp_data.append({"Categoría": "Hogar", "Persona": persona2, "Monto": res_hogar.get("pago_p2") or 0})
    if comp_data:
        df_comp = pd.DataFrame(comp_data)
        fig = px.bar(
            df_comp,
            x="Categoría",
            y="Monto",
            color="Persona",
            barmode="group",
            color_discrete_sequence=["#0EA5E9", "#10B981"],
        )
        fig.update_yaxes(tickprefix="$", separatethousands=True)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay gastos para comparar.")

    # Progreso por categoría (antes "Resumen de deudas por viaje")
    st.markdown("### Progreso de pago por categoría")
    col_pg1, col_pg2 = st.columns(2)
    with col_pg1:
        st.markdown("**Viajes**")
        st.progress(
            (res_viaje.get("porcentaje_pagado", 0.0) or 0.0) / 100.0,
            text=f"{res_viaje.get('porcentaje_pagado', 0.0):.1f}% pagado",
        )
    with col_pg2:
        st.markdown("**Hogar**")
        st.progress(
            (res_hogar.get("porcentaje_pagado", 0.0) or 0.0) / 100.0,
            text=f"{res_hogar.get('porcentaje_pagado', 0.0):.1f}% pagado",
        )

    # Resumen de deudas por categoría: viajes + fila Hogar
    st.markdown("### Resumen de deudas por categoría")
    filas_resumen = []

    # Filas por cada viaje
    if not df_viajes.empty:
        for _, v in df_viajes.iterrows():
            vid = int(v["id"])
            if not df_viaje.empty and "viaje_id" in df_viaje.columns:
                gastos_v = df_viaje[df_viaje["viaje_id"] == vid]
            else:
                gastos_v = df_viaje.copy()
            if not df_pagos_viaje.empty and "viaje_id" in df_pagos_viaje.columns:
                pagos_v = df_pagos_viaje[df_pagos_viaje["viaje_id"] == vid]
            else:
                pagos_v = df_pagos_viaje.copy()
            _, res_v = calcular_balance(gastos_v, pagos_v, persona1, persona2)
            saldo = float(res_v.get("saldo_pendiente", 0.0) or 0.0)
            deuda = float(res_v.get("deuda_original", 0.0) or 0.0)
            abonado = float(res_v.get("abonos_aplicados", 0.0) or 0.0)
            pct = float(res_v.get("porcentaje_pagado", 0.0) or 0.0)
            if deuda > 0 and pct > 0 and pct < 100:
                estado = "Parcial"
            elif saldo <= 0 or pct >= 100:
                estado = "Saldado"
            else:
                estado = "Pendiente"
            nombre_viaje = str(v.get("nombre", f"Viaje #{vid}"))
            if v.get("destino"):
                nombre_viaje += f" ({v.get('destino')})"
            filas_resumen.append({
                "Categoria": nombre_viaje,
                "Deuda": deuda,
                "Abonado": abonado,
                "Saldo": saldo,
                "Estado": estado,
                "Progreso": pct,
            })

    # Fila Hogar
    d_h = float(res_hogar.get("deuda_original", 0.0) or 0.0)
    a_h = float(res_hogar.get("abonos_aplicados", 0.0) or 0.0)
    s_h = float(res_hogar.get("saldo_pendiente", 0.0) or 0.0)
    pct_h = float(res_hogar.get("porcentaje_pagado", 0.0) or 0.0)
    if d_h > 0 and pct_h > 0 and pct_h < 100:
        estado_h = "Parcial"
    elif s_h <= 0 or pct_h >= 100:
        estado_h = "Saldado"
    else:
        estado_h = "Pendiente"
    filas_resumen.append({
        "Categoria": "Hogar",
        "Deuda": d_h,
        "Abonado": a_h,
        "Saldo": s_h,
        "Estado": estado_h,
        "Progreso": pct_h,
    })

    if not filas_resumen:
        st.info("Aún no hay datos de deudas.")
    else:
        df_res = pd.DataFrame(filas_resumen)
        df_show = df_res.copy()
        df_show["Deuda"] = df_show["Deuda"].apply(formatear_cop)
        df_show["Abonado"] = df_show["Abonado"].apply(formatear_cop)
        df_show["Saldo"] = df_show["Saldo"].apply(formatear_cop)
        df_show["Progreso"] = df_show["Progreso"].map(lambda v: f"{float(v):.1f}%")
        st.dataframe(df_show[["Categoria", "Deuda", "Abonado", "Saldo", "Estado", "Progreso"]], use_container_width=True)

    st.markdown("### Exportar datos")
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        if df_gastos.empty:
            st.info("No hay datos para exportar.")
        else:
            csv_bytes = df_gastos.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Descargar gastos en CSV",
                data=csv_bytes,
                file_name="gastos_compartidos.csv",
                mime="text/csv",
            )
    with col_e2:
        reporte_texto = generar_reporte_texto(
            persona1=persona1,
            persona2=persona2,
            df_gastos=df_gastos,
            df_pagos=df_pagos,
        )
        st.download_button(
            "📄 Descargar reporte resumen",
            data=reporte_texto,
            file_name="reporte_gastos.txt",
            mime="text/plain",
        )


def main():
    st.set_page_config(
        page_title="Gastos compartidos",
        page_icon="👩🏻‍❤️‍👨🏻",
        layout="wide",
    )

    st.markdown(
        """
        <style>
        /* Tarjetas: fondos claros por sección */
        .stMetric > div {
            background-color: #F1F5F9;
            border-radius: 12px;
            padding: 12px;
            border: 1px solid #E2E8F0;
        }
        /* Botones: color primario elegante */
        .stButton > button, .stDownloadButton > button {
            background: linear-gradient(90deg, #0EA5E9, #38BDF8);
            color: #fff;
            border-radius: 999px;
            border: none;
            font-weight: 600;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            filter: brightness(1.05);
        }
        /* Barras de progreso */
        .stProgress > div > div > div {
            background: linear-gradient(90deg, #0EA5E9, #38BDF8);
        }
        @media (max-width: 640px) {
            .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 1rem; padding-right: 1rem; }
            .stButton > button { min-height: 44px; padding: 0.5rem 1rem; }
            .stSelectbox > div > div { min-height: 44px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar: estado de conexión
    st.sidebar.title("⚙️ Configuración")
    try:
        _ = get_spreadsheet()
        st.sidebar.markdown("**Estado de Google Sheets:** ✅ Conectado")
    except Exception as e:
        st.sidebar.markdown("**Estado de Google Sheets:** ❌ Error")
        st.sidebar.error(
            "No se pudo conectar a Google Sheets. "
            "Revisa tus credenciales en `secrets.toml` y que el Sheet exista "
            f"({SPREADSHEET_NAME}).\n\nDetalle técnico: " + str(e)
        )
        st.stop()

    # Cargar configuración
    config = load_config_dict()
    persona1 = config.get("persona1", "Persona 1")
    persona2 = config.get("persona2", "Persona 2")

    st.sidebar.subheader("👥 Personas")
    with st.sidebar.form("form_config_personas"):
        nombre1 = st.text_input("Nombre persona 1", value=persona1)
        nombre2 = st.text_input("Nombre persona 2", value=persona2)
        guardar_nombres = st.form_submit_button("Guardar nombres")
        if guardar_nombres:
            set_config_value("persona1", nombre1.strip() or "Persona 1")
            set_config_value("persona2", nombre2.strip() or "Persona 2")
            st.sidebar.success("Nombres actualizados. Recarga o continúa usando la app.")
            persona1 = nombre1.strip() or "Persona 1"
            persona2 = nombre2.strip() or "Persona 2"

    if st.sidebar.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("📤 Exportar")
    df_gastos_export = load_gastos_df()
    if not df_gastos_export.empty:
        csv_bytes = df_gastos_export.to_csv(index=False).encode("utf-8")
        st.sidebar.download_button(
            "Descargar CSV",
            data=csv_bytes,
            file_name="gastos_compartidos.csv",
            mime="text/csv",
            key="sidebar_csv",
        )
    reporte_texto = generar_reporte_texto(
        persona1=persona1,
        persona2=persona2,
        df_gastos=df_gastos_export,
        df_pagos=load_pagos_df(),
    )
    st.sidebar.download_button(
        "Descargar Reporte",
        data=reporte_texto,
        file_name="reporte_gastos.txt",
        mime="text/plain",
        key="sidebar_reporte",
    )
    st.sidebar.caption("v1.0 | Datos en Google Sheets")

    st.title("👩🏻‍❤️‍👨🏻 Gestor de Gastos Compartidos")
    st.write(
        f"Gestiona y divide fácilmente los gastos entre **{persona1}** y **{persona2}**."
    )

    tabs = st.tabs(["🧳 Viaje", "🏠 Hogar", "🏦 Préstamos", "📊 Resumen Global"])

    # Tab de viaje trabajará sobre el viaje activo
    with tabs[0]:
        # Cargar viajes y determinar viaje activo
        df_viajes = load_viajes_df()
        viaje_activo = None
        if not df_viajes.empty and "estado" in df_viajes.columns:
            activos = df_viajes[
                df_viajes["estado"].astype(str).str.lower() == "activo"
            ]
            if not activos.empty:
                viaje_activo = activos.iloc[0]

        col_form, col_resumen = st.columns([1, 2])
        with col_form:
            st.subheader("✈️ Gestión de viaje")
            if viaje_activo is None:
                st.info("No hay un viaje activo. Crea uno para empezar a registrar gastos.")
                with st.form("form_crear_viaje"):
                    nombre_viaje = st.text_input("Nombre del viaje")
                    destino_viaje = st.text_input("Destino")
                    rango_fechas = st.date_input(
                        "Fechas del viaje",
                        (date.today(), date.today()),
                    )
                    crear = st.form_submit_button("Crear viaje")
                    if crear:
                        if not nombre_viaje:
                            st.error("Ingresa al menos un nombre para el viaje.")
                        else:
                            if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
                                f_ini, f_fin = rango_fechas
                            else:
                                f_ini = f_fin = rango_fechas
                            crear_viaje(
                                nombre=nombre_viaje,
                                destino=destino_viaje,
                                fecha_inicio=f_ini,
                                fecha_fin=f_fin,
                            )
                            st.success("Viaje creado correctamente.")
                            st.rerun()
            else:
                st.markdown(
                    f"**Viaje activo:** {viaje_activo.get('nombre', '')} – "
                    f"{viaje_activo.get('destino', '')}"
                )
                fi = viaje_activo.get("fecha_inicio")
                ff = viaje_activo.get("fecha_fin")
                if fi and ff:
                    st.caption(f"{fi} → {ff}")

                render_form_gasto(
                    "viaje",
                    persona1,
                    persona2,
                    viaje_id=int(viaje_activo["id"]),
                )

                # Bloque para cerrar viaje
                with st.expander("Cerrar este viaje", expanded=False):
                    df_gastos = load_gastos_df()
                    df_pagos = load_pagos_df()

                    if not df_gastos.empty:
                        mask_viaje = pd.Series([True] * len(df_gastos))
                        if "categoria" in df_gastos.columns:
                            mask_viaje &= df_gastos["categoria"] == "viaje"
                        if "viaje_id" in df_gastos.columns:
                            mask_viaje &= df_gastos["viaje_id"] == int(viaje_activo["id"])
                        df_viaje_gastos = df_gastos[mask_viaje].copy()
                    else:
                        df_viaje_gastos = df_gastos.copy()

                    if not df_pagos.empty:
                        mask_pagos = pd.Series([True] * len(df_pagos))
                        if "categoria" in df_pagos.columns:
                            mask_pagos &= df_pagos["categoria"] == "viaje"
                        if "viaje_id" in df_pagos.columns:
                            mask_pagos &= df_pagos["viaje_id"] == int(viaje_activo["id"])
                        df_viaje_pagos = df_pagos[mask_pagos].copy()
                    else:
                        df_viaje_pagos = df_pagos.copy()
                    _, resumen_viaje_activo = calcular_balance(
                        df_viaje_gastos, df_viaje_pagos, persona1, persona2
                    )
                    st.write(
                        f"Deuda original: {formatear_cop(resumen_viaje_activo['deuda_original'])}"
                    )
                    st.write(
                        f"Abonado: {formatear_cop(resumen_viaje_activo['abonos_aplicados'])}"
                    )
                    st.write(
                        f"Saldo pendiente: {formatear_cop(resumen_viaje_activo['saldo_pendiente'])}"
                    )
                    st.progress(
                        (resumen_viaje_activo.get("porcentaje_pagado", 0.0) or 0.0) / 100.0
                    )

                    with st.form("form_cerrar_viaje"):
                        estado_cierre = st.radio(
                            "Estado al cerrar",
                            ["Saldado", "Pendiente"],
                            index=0
                            if resumen_viaje_activo.get("saldo_pendiente", 0.0) == 0
                            else 1,
                        )
                        cerrar_btn = st.form_submit_button("Cerrar viaje")
                        if cerrar_btn:
                            saldado_flag = estado_cierre == "Saldado"
                            balance_final = (
                                0.0
                                if saldado_flag
                                else float(resumen_viaje_activo.get("saldo_pendiente", 0.0) or 0.0)
                            )
                            cerrar_viaje(
                                viaje_id=int(viaje_activo["id"]),
                                saldado=saldado_flag,
                                balance_final=balance_final,
                            )
                            st.success("Viaje cerrado correctamente.")
                            st.rerun()

        with col_resumen:
            if viaje_activo is None:
                st.info("Cuando tengas un viaje activo verás aquí su resumen de gastos.")
            else:
                render_resumen_categoria(
                    "viaje",
                    persona1,
                    persona2,
                    viaje_id=int(viaje_activo["id"]),
                )

        # Historial de viajes cerrados
        st.markdown("### 📚 Historial de viajes cerrados")
        df_cerrados = pd.DataFrame()
        if not df_viajes.empty:
            df_cerrados = df_viajes[
                df_viajes["estado"].astype(str).str.lower() == "cerrado"
            ].copy()
        with st.expander("Ver viajes cerrados", expanded=False):
            if df_cerrados.empty:
                st.info("Aún no hay viajes cerrados.")
            else:
                df_cerrados["estado_label"] = df_cerrados["saldado"].apply(
                    lambda v: "Saldado" if str(v).lower() == "saldado" else "Pendiente"
                )
                mostrar = df_cerrados[
                    ["nombre", "destino", "fecha_inicio", "fecha_fin", "estado_label", "balance_final"]
                ].copy()
                mostrar.rename(
                    columns={
                        "nombre": "Nombre",
                        "destino": "Destino",
                        "fecha_inicio": "Inicio",
                        "fecha_fin": "Fin",
                        "estado_label": "Estado",
                        "balance_final": "Balance final",
                    },
                    inplace=True,
                )
                mostrar["Balance final"] = mostrar["Balance final"].apply(formatear_cop)
                st.dataframe(mostrar, use_container_width=True)

    with tabs[1]:
        col_form, col_resumen = st.columns([1, 2])
        with col_form:
            render_form_gasto("hogar", persona1, persona2)
        with col_resumen:
            render_resumen_categoria("hogar", persona1, persona2)

    with tabs[2]:
        render_prestamos_tab(persona1, persona2)

    with tabs[3]:
        render_resumen_global(persona1, persona2)
        st.markdown("---")
        render_pagos_section(persona1, persona2)


if __name__ == "__main__":
    main()


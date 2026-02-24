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
    balance_p1 = balance_sin_abonos - abonos_p1_a_p2 + abonos_p2_a_p1

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
        porcentaje_pagado = (abonos_aplicados / deuda_original) * 100.0
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
    }


def mostrar_mensaje_balance(balance_p1: float, persona1: str, persona2: str) -> None:
    """Muestra un mensaje grande y colorido con el balance."""
    if abs(balance_p1) < 1:
        mensaje = f"✅ Están a mano, nadie le debe a nadie."
        color = "#F59E0B"
    elif balance_p1 > 0:
        mensaje = (
            f"💰 {persona2} le debe {formatear_cop(balance_p1)} a {persona1}"
        )
        color = "#10B981"
    else:
        mensaje = (
            f"💰 {persona1} le debe {formatear_cop(abs(balance_p1))} a {persona2}"
        )
        color = "#EF4444"

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
    col_ec1, col_ec2, col_ec3 = st.columns(3)
    col_ec1.metric("Deuda original", formatear_cop(resumen.get("deuda_original", 0.0)))
    col_ec2.metric("Abonado", formatear_cop(resumen.get("abonos_aplicados", 0.0)))
    col_ec3.metric("Saldo pendiente", formatear_cop(resumen.get("saldo_pendiente", 0.0)))

    deuda_original = float(resumen.get("deuda_original", 0.0) or 0.0)
    porcentaje_pagado = float(resumen.get("porcentaje_pagado", 0.0) or 0.0)
    saldo_pendiente = float(resumen.get("saldo_pendiente", 0.0) or 0.0)
    deudor = resumen.get("deudor")
    acreedor = resumen.get("acreedor")

    progreso = porcentaje_pagado / 100.0 if deuda_original > 0 else 0.0
    st.progress(progreso, text=f"{porcentaje_pagado:,.1f}% pagado" if deuda_original > 0 else "Sin deuda")

    if deuda_original <= 0 or saldo_pendiente <= 0:
        st.success("Esta categoría está completamente saldada entre ambas personas.")
    else:
        st.info(
            f"{deudor} aún le debe {formatear_cop(saldo_pendiente)} a {acreedor} "
            f"(abonó {formatear_cop(resumen.get('abonos_aplicados', 0.0))} "
            f"de {formatear_cop(deuda_original)})."
        )

    st.markdown("### 💸 Registrar pago o abono")
    with st.form(f"form_pago_{key_prefix}"):
        fecha_pago = st.date_input(
            "Fecha del pago",
            value=date.today(),
            key=f"fecha_pago_{key_prefix}",
        )

        if deudor in (persona1, persona2):
            idx_default = 0 if deudor == persona1 else 1
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
        nota = st.text_input("Nota (opcional)", key=f"nota_pago_{key_prefix}")

        submitted = st.form_submit_button("Registrar pago")
        if submitted:
            if deuda_original <= 0:
                st.error("Actualmente no hay deuda pendiente en esta categoría.")
            else:
                monto = saldo_pendiente if tipo_pago == "Pagar todo" else monto_input
                if monto <= 0:
                    st.error("El monto debe ser mayor a cero.")
                else:
                    add_pago(
                        fecha=fecha_pago,
                        quien_paga=quien_paga,
                        quien_recibe=quien_recibe,
                        monto=monto,
                        categoria=categoria,
                        nota=nota,
                        viaje_id=viaje_id,
                    )
                    st.success("Pago registrado correctamente.")
                    st.rerun()

    st.markdown("### 🕒 Historial de pagos")
    if df_pagos_cat.empty:
        st.info("Aún no hay pagos registrados para esta categoría.")
    else:
        df_hist = df_pagos_cat.copy()
        if "fecha" in df_hist.columns:
            df_hist["fecha_dt"] = pd.to_datetime(df_hist["fecha"], errors="coerce")
            df_hist.sort_values("fecha_dt", inplace=True)
        df_hist["monto"] = df_hist["monto"].apply(formatear_cop)
        df_hist.rename(
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
            df_hist[["Fecha", "Quién paga", "Quién recibe", "Monto", "Nota"]],
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
                color_discrete_sequence=["#FF6B35", "#FFA726"],
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
                color_discrete_sequence=px.colors.sequential.Oranges,
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
    """Sección global para registrar pagos/abonos generales y ver historial."""
    st.subheader("💸 Pagos / Abonos entre personas")
    col1, col2 = st.columns(2)
    with col1:
        with st.form("form_pagos"):
            fecha = st.date_input("Fecha del pago", value=date.today())
            quien_paga = st.selectbox("Quién paga", [persona1, persona2])
            quien_recibe = persona2 if quien_paga == persona1 else persona1
            monto = st.number_input(
                "Monto (COP)",
                min_value=0.0,
                step=1000.0,
                format="%.0f",
            )
            categoria_pago = st.selectbox(
                "Aplica a la categoría",
                ["general", "viaje", "hogar"],
                index=0,
            )
            nota = st.text_input("Nota (opcional)")
            submitted_pago = st.form_submit_button("Registrar pago")
            if submitted_pago:
                if monto <= 0:
                    st.error("El monto debe ser mayor a cero.")
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
                    st.success("Pago registrado correctamente.")

    with col2:
        with st.spinner("Cargando historial de pagos..."):
            df_pagos = load_pagos_df()
        if df_pagos.empty:
            st.info("Aún no hay pagos registrados.")
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
            st.dataframe(
                df_pagos_mostrar[["Fecha", "Quién paga", "Quién recibe", "Monto", "Categoría", "Nota"]],
                use_container_width=True,
            )


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


def render_resumen_global(persona1: str, persona2: str) -> None:
    """Tab de resumen global combinando ambas categorías."""
    with st.spinner("Cargando datos globales..."):
        df_gastos = load_gastos_df()
        df_pagos = load_pagos_df()
        df_viajes = load_viajes_df()

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

    # Global: todos los gastos y todos los pagos (incluye "general")
    bal_global, res_global = calcular_balance(df_gastos, df_pagos, persona1, persona2)

    st.subheader("Resumen por categoría")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Balance viajes", formatear_cop(res_viaje["saldo_pendiente"]))
    with col2:
        st.metric("Balance hogar", formatear_cop(res_hogar["saldo_pendiente"]))
    with col3:
        st.metric("Balance total", formatear_cop(res_global["saldo_pendiente"]))

    st.markdown("### Balance global")
    mostrar_mensaje_balance(bal_global, persona1, persona2)

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

    # Desglose por viaje
    st.markdown("### Resumen de deudas por viaje")
    filas_resumen_viajes = []
    if not df_viajes.empty:
        for _, v in df_viajes.iterrows():
            vid = int(v["id"])
            # Filtrar por viaje_id de forma segura
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
            estado_sheet = str(v.get("saldado", "")).lower()
            if estado_sheet == "saldado":
                estado_label = "Saldado"
            elif saldo > 0:
                estado_label = "Pendiente"
            else:
                estado_label = "Saldado"
            filas_resumen_viajes.append(
                {
                    "Viaje": v.get("nombre", f"Viaje #{vid}"),
                    "Destino": v.get("destino", ""),
                    "Deuda": res_v.get("deuda_original", 0.0) or 0.0,
                    "Abonado": res_v.get("abonos_aplicados", 0.0) or 0.0,
                    "Saldo": saldo,
                    "Estado": estado_label,
                    "Progreso": res_v.get("porcentaje_pagado", 0.0) or 0.0,
                }
            )

    if not filas_resumen_viajes:
        st.info("Aún no hay viajes registrados.")
    else:
        df_res_viajes = pd.DataFrame(filas_resumen_viajes)
        df_res_viajes["Deuda"] = df_res_viajes["Deuda"].apply(formatear_cop)
        df_res_viajes["Abonado"] = df_res_viajes["Abonado"].apply(formatear_cop)
        df_res_viajes["Saldo"] = df_res_viajes["Saldo"].apply(formatear_cop)
        df_res_viajes["Progreso"] = df_res_viajes["Progreso"].map(
            lambda v: f"{float(v):.1f}%"
        )
        st.dataframe(df_res_viajes, use_container_width=True)

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
        /* Tarjetas de métricas */
        .stMetric > div {
            background-color: #111827;
            border-radius: 12px;
            padding: 12px;
            border: 1px solid #1E293B;
        }
        /* Botones principales en dorado */
        .stButton > button, .stDownloadButton > button {
            background: linear-gradient(90deg, #F59E0B, #fbbf24);
            color: #0A0F1C;
            border-radius: 999px;
            border: none;
            font-weight: 600;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            filter: brightness(1.05);
        }
        /* Progresos */
        .stProgress > div > div > div {
            background-color: #F59E0B;
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

    st.title("👩🏻‍❤️‍👨🏻 Gestor de Gastos Compartidos")
    st.write(
        f"Gestiona y divide fácilmente los gastos entre **{persona1}** y **{persona2}**."
    )

    tabs = st.tabs(["🧳 Viaje", "🏠 Hogar", "📊 Resumen Global"])

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
        render_resumen_global(persona1, persona2)
        st.markdown("---")
        render_pagos_section(persona1, persona2)


if __name__ == "__main__":
    main()


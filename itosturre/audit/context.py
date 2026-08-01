"""Contextualización material y territorial de fuentes normativas."""


def vvca_contextualizacion(source_file: str) -> str:
    s = source_file.lower()
    if "cpeum" in s or "estados unidos mexicanos" in s:
        return "Constitucional · Federal · Aplicable a todo el sistema jurídico"
    if "cnpp" in s or "procedpenales" in s or "procedimientos penales" in s:
        return "Procesal Penal · Nacional · PJF y juzgados locales acreditados CNPP"
    if "penal federal" in s:
        return "Penal sustantivo · Federal · PJF"
    if "delincuencia organizada" in s:
        return "Penal especial · Federal · LFDO — delitos del catálogo art. 2"
    if "extincion de dominio" in s or "extinción" in s:
        return "Extinción de dominio · Federal · Proceso civil especial autónomo"
    if "general de victimas" in s or "víctimas" in s:
        return "Penal/DDHH · Federal · Derechos de víctimas en toda causa penal"
    if "ejecucion penal" in s or "ejecución penal" in s:
        return "Ejecución de sanciones · Federal · Post-sentencia"
    if "convencion americana" in s or "cadh" in s:
        return "DDHH · Internacional · Control de convencionalidad obligatorio (art. 1° CPEUM)"
    if "pacto internacional" in s or "pidcp" in s:
        return "DDHH · ONU · Control de convencionalidad — aplica en amparo"
    if "amparo" in s:
        return "Amparo · Federal · Juzgados de Distrito y TCC"
    if any(term in s for term in (
        "lopjf",
        "orgánica del poder judicial",
        "organica del poder judicial",
        "organicopoder",
        "reglamentoorgan",
    )):
        return "Orgánica · Federal · Competencia PJF"
    if "fiscal de la federacion" in s or "c.f.f" in s:
        return "Fiscal · Federal · SAT / contribuciones federales"
    if "fiscal del estado de jalisco" in s:
        return "Fiscal · Local · Jalisco"
    if "impuesto sobre la renta" in s:
        return "Fiscal · Federal · ISR"
    if "impuesto al valor agregado" in s:
        return "Fiscal · Federal · IVA"
    if "trabajo" in s or "lft" in s:
        return "Laboral · Federal · JFCA / Tribunales Laborales"
    if "seguro social" in s:
        return "Seguridad Social · Federal · IMSS"
    if "civil federal" in s:
        return "Civil · Federal"
    if "jalisco" in s:
        return "Local · Estado de Jalisco"
    if "nuevo leon" in s or "nuevo león" in s:
        return "Local · Estado de Nuevo León"
    return "Normativo · Verificar ámbito de aplicación específico"


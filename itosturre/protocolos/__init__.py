"""Protocolos de materia: conocimiento de fondo que complementa —no sustituye— a agentes
jurídicos que ya tienen su rol, sus reglas y su formato de salida.

Componente genérico de Itosturre: contrato (G1), lint "complemento, no sustituto" (G2) y
verificación de citas contra el corpus local (G3) y contra la evidencia del SJF (G4). Los
protocolos que produce son entregables del sistema de destino y no viven en este repo.
Ver la CLI scripts/protocolo_gates.py.
"""
from itosturre.protocolos.contrato import MATERIAS, SECCIONES, Hallazgo, validar_esquema
from itosturre.protocolos.gates import Reporte, correr_gates, huella

__all__ = ["MATERIAS", "SECCIONES", "Hallazgo", "Reporte", "correr_gates", "huella", "validar_esquema"]

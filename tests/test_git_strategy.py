"""Pruebas de scripts/git_strategy.sh y del hook .githooks/pre-commit.

Cada prueba crea un repositorio git temporal aislado (configuración global vacía,
identidad propia) con una política de datos mínima. Nunca toca el repositorio real.
En Windows se usa el bash de Git for Windows: el ``bash.exe`` de System32 lanza WSL.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _git_bash() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    if os.name == "nt":
        # git puede resolverse como …\Git\cmd\git.exe o …\Git\mingw64\bin\git.exe:
        # se sube hasta la raíz de Git for Windows, que contiene bin\bash.exe.
        for base in list(Path(git).resolve().parents)[:4]:
            for candidato in (base / "bin" / "bash.exe", base / "usr" / "bin" / "bash.exe"):
                if candidato.is_file() and "system32" not in str(candidato).lower():
                    return str(candidato)
        return None
    return shutil.which("bash")


BASH = _git_bash()
POLITICA_MINIMA = {
    "version": 1,
    "required_gitignore_rules": [".env"],
    "forbidden_tracked_prefixes": ["secreto/"],
    "forbidden_tracked_files": [".env"],
    "tracked_case_fixtures": [],
    "tracked_validation_fixtures": [],
    "regression_case_fixtures": [],
}


def _copiar_lf(origen: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(origen.read_bytes().replace(b"\r\n", b"\n"))


@unittest.skipUnless(BASH, "requiere git y el bash de Git (o bash en POSIX)")
class GitStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        self.root.mkdir()
        (base / "gitconfig").write_text("", encoding="utf-8")

        self.env = {k: v for k, v in os.environ.items() if not k.startswith("ITOS_")}
        self.env.update(
            {
                "GIT_CONFIG_GLOBAL": str(base / "gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "Prueba",
                "GIT_AUTHOR_EMAIL": "prueba@example.invalid",
                "GIT_COMMITTER_NAME": "Prueba",
                "GIT_COMMITTER_EMAIL": "prueba@example.invalid",
                "PYTHON": sys.executable.replace("\\", "/"),
                # En Windows, el runtime MSYS expande comodines en argv antes de que bash
                # los vea; sin esto '*.txt' llegaría al script ya convertido en 'a.txt'.
                "MSYS": "noglob",
            }
        )

        _copiar_lf(REPO / "scripts" / "git_strategy.sh", self.root / "scripts" / "git_strategy.sh")
        _copiar_lf(
            REPO / "scripts" / "check_sensitive_paths.py",
            self.root / "scripts" / "check_sensitive_paths.py",
        )
        (self.root / "config").mkdir()
        (self.root / "config" / "data-policy.json").write_text(
            json.dumps(POLITICA_MINIMA), encoding="utf-8"
        )
        (self.root / ".gitignore").write_text(".env\n", encoding="utf-8")
        (self.root / "README.md").write_text("inicial\n", encoding="utf-8")

        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    # ── utilidades ────────────────────────────────────────────────────────────
    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=self.root, env=self.env, check=check,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )

    def script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [BASH, "scripts/git_strategy.sh", *args], cwd=self.root, env=self.env,
            capture_output=True, text=True, encoding="utf-8",
            stdin=subprocess.DEVNULL, timeout=120,
        )

    def rama(self) -> str:
        return self.git("branch", "--show-current").stdout.strip()

    def commits(self, ref: str = "HEAD") -> int:
        return int(self.git("rev-list", "--count", ref).stdout.strip())

    def indice_vacio(self) -> bool:
        return self.git("diff", "--cached", "--quiet", check=False).returncode == 0

    def escribir(self, nombre: str, texto: str = "contenido\n") -> None:
        ruta = self.root / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")

    def rama_con_commit(self, rama: str = "feat/demo") -> None:
        self.assertEqual(self.script("0", rama).returncode, 0)
        self.escribir("a.txt")
        resultado = self.script("1", "-m", "feat: añade a", "--", "a.txt")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    # ── paso 0 ────────────────────────────────────────────────────────────────
    def test_paso0_rechaza_nombres_invalidos(self) -> None:
        for nombre in ("main", "hotfix/x", "feat/Mayus", "feat/", "fix/-x", "feat/a b"):
            with self.subTest(nombre=nombre):
                self.assertNotEqual(self.script("0", nombre).returncode, 0)
                self.assertEqual(self.rama(), "main")

    def test_paso0_crea_y_reutiliza_rama(self) -> None:
        self.assertEqual(self.script("0", "feat/demo").returncode, 0)
        self.assertEqual(self.rama(), "feat/demo")
        self.git("checkout", "-q", "main")
        self.assertEqual(self.script("0", "feat/demo").returncode, 0)
        self.assertEqual(self.rama(), "feat/demo")

    def test_paso0_acepta_itos_branch_por_compatibilidad(self) -> None:
        self.env["ITOS_BRANCH"] = "fix/compat"
        self.assertEqual(self.script("0").returncode, 0)
        self.assertEqual(self.rama(), "fix/compat")

    # ── paso 1 ────────────────────────────────────────────────────────────────
    def test_paso1_rechaza_commit_en_main(self) -> None:
        self.escribir("README.md", "cambio\n")
        resultado = self.script("1", "-m", "x", "--", "README.md")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("regla absoluta 4", resultado.stderr)
        self.assertEqual(self.commits(), 1)
        self.assertTrue(self.indice_vacio())

    def test_paso1_exige_mensaje_y_rutas(self) -> None:
        self.script("0", "feat/demo")
        self.escribir("a.txt")
        for args in (("1", "--", "a.txt"), ("1", "-m", "x"), ("1", "-m", "x", "--"), ("1", "-m")):
            with self.subTest(args=args):
                self.assertNotEqual(self.script(*args).returncode, 0)
        self.assertEqual(self.commits(), 1)

    def test_paso1_rechaza_rutas_globales(self) -> None:
        self.script("0", "feat/demo")
        self.escribir("a.txt")
        for ruta in (".", "-A", "*.txt", ":/"):
            with self.subTest(ruta=ruta):
                self.assertNotEqual(self.script("1", "-m", "x", "--", ruta).returncode, 0)
                self.assertTrue(self.indice_vacio())
        self.assertEqual(self.commits(), 1)

    def test_paso1_commitea_solo_rutas_declaradas_con_su_mensaje(self) -> None:
        self.script("0", "feat/demo")
        self.escribir("a.txt")
        self.escribir("b.txt")
        resultado = self.script("1", "-m", "feat: añade a", "-m", "Detalle del cambio.", "--", "a.txt")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.commits(), 2)
        archivos = self.git("show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(archivos, ["a.txt"])
        mensaje = self.git("log", "-1", "--format=%B").stdout
        self.assertTrue(mensaje.startswith("feat: añade a"))
        self.assertIn("Detalle del cambio.", mensaje)
        self.assertIn("b.txt", self.git("status", "--short").stdout)

    def test_paso1_rechaza_indice_preparado_de_antemano(self) -> None:
        self.script("0", "feat/demo")
        self.escribir("a.txt")
        self.escribir("b.txt")
        self.git("add", "b.txt")
        self.assertNotEqual(self.script("1", "-m", "x", "--", "a.txt").returncode, 0)
        self.assertEqual(self.commits(), 1)

    def test_paso1_admite_lo_preparado_dentro_de_las_rutas_declaradas(self) -> None:
        self.script("0", "feat/demo")
        self.escribir("hooks/pre-commit", "#!/usr/bin/env bash\nexit 0\n")
        self.git("add", "hooks/pre-commit")
        self.git("update-index", "--chmod=+x", "hooks/pre-commit")
        # Con core.filemode=true (Linux, macOS) el `git add` del paso 1 toma el modo del
        # disco y descartaría el +x del índice; en Windows (filemode=false) no tiene efecto.
        (self.root / "hooks" / "pre-commit").chmod(0o755)
        resultado = self.script("1", "-m", "chore: hook", "--", "hooks/")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        modo = self.git("ls-files", "-s", "hooks/pre-commit").stdout.split()[0]
        self.assertEqual(modo, "100755")

    def test_paso1_deshace_la_preparacion_si_falla_la_politica(self) -> None:
        self.script("0", "feat/demo")
        self.escribir("secreto/datos.txt")
        resultado = self.script("1", "-m", "x", "--", "secreto/datos.txt")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("Política de datos", resultado.stderr)
        self.assertEqual(self.commits(), 1)
        self.assertTrue(self.indice_vacio())

    # ── paso 2 ────────────────────────────────────────────────────────────────
    def test_paso2_no_publica_main(self) -> None:
        resultado = self.script("2")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("no main", resultado.stderr)

    # ── paso 3 ────────────────────────────────────────────────────────────────
    def test_paso3_sin_terminal_ni_confirmacion_aborta(self) -> None:
        self.rama_con_commit()
        resultado = self.script("3")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("--confirmar", resultado.stderr)
        self.assertEqual(self.rama(), "feat/demo")
        self.assertEqual(self.commits("main"), 1)

    def test_paso3_confirmacion_de_otra_rama_aborta(self) -> None:
        self.rama_con_commit()
        self.assertNotEqual(self.script("3", "--confirmar", "feat/otra").returncode, 0)
        self.assertEqual(self.commits("main"), 1)

    def test_paso3_rechaza_cambios_sin_commitear(self) -> None:
        self.rama_con_commit()
        self.escribir("a.txt", "modificado\n")
        self.assertNotEqual(self.script("3", "--confirmar", "feat/demo").returncode, 0)
        self.assertEqual(self.commits("main"), 1)

    def test_paso3_fusiona_no_ff_tras_gates(self) -> None:
        self.rama_con_commit()
        resultado = self.script(
            "3", "--confirmar", "feat/demo", "-m", "Co-Authored-By: Prueba <prueba@example.invalid>"
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.rama(), "main")
        padres = self.git("log", "-1", "--format=%P").stdout.split()
        self.assertEqual(len(padres), 2)
        mensaje = self.git("log", "-1", "--format=%B").stdout
        self.assertTrue(mensaje.startswith("Merge feat/demo: feat: añade a"))
        self.assertIn("Co-Authored-By: Prueba", mensaje)

    def test_paso3_fusiona_sin_parrafos_extra(self) -> None:
        # Sin -m la lista de párrafos queda vacía; con `set -u`, el bash 3.2 de macOS
        # abortaba al expandirla ("extra[@]: unbound variable").
        self.rama_con_commit()
        resultado = self.script("3", "--confirmar", "feat/demo")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.rama(), "main")
        self.assertEqual(len(self.git("log", "-1", "--format=%P").stdout.split()), 2)
        self.assertEqual(self.git("log", "-1", "--format=%B").stdout.strip(), "Merge feat/demo: feat: añade a")

    # ── hook ─────────────────────────────────────────────────────────────────
    def test_hook_bloquea_commit_directo_en_main(self) -> None:
        hook = self.root / ".githooks" / "pre-commit"
        _copiar_lf(REPO / ".githooks" / "pre-commit", hook)
        hook.chmod(0o755)
        self.git("config", "core.hooksPath", ".githooks")

        self.escribir("README.md", "cambio directo\n")
        self.git("add", "README.md")
        bloqueado = self.git("commit", "-m", "directo", check=False)
        self.assertNotEqual(bloqueado.returncode, 0)
        self.assertIn("bloqueado", bloqueado.stderr)
        self.assertEqual(self.commits(), 1)

        self.git("checkout", "-q", "-b", "feat/demo")
        permitido = self.git("commit", "-m", "en rama", check=False)
        self.assertEqual(permitido.returncode, 0, permitido.stderr)


if __name__ == "__main__":
    unittest.main()

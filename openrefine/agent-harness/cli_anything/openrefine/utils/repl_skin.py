from __future__ import annotations

try:
    from prompt_toolkit import PromptSession
except Exception:  # pragma: no cover
    PromptSession = None


class ReplSkin:
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version

    def print_banner(self) -> None:
        print(f"{self.name} CLI-Anything {self.version}")
        print("Type help for commands, exit to quit.")

    def create_prompt_session(self):
        if PromptSession:
            return PromptSession()
        return None

    def get_input(self, session, project_name=None, modified=False) -> str:
        marker = "*" if modified else ""
        prompt = f"{self.name}"
        if project_name:
            prompt += f"[{project_name}{marker}]"
        prompt += "> "
        if session:
            return session.prompt(prompt)
        return input(prompt)

    def help(self, commands: dict[str, str]) -> None:
        for command, description in commands.items():
            print(f"{command:28} {description}")

    def success(self, message: str) -> None:
        print(f"OK: {message}")

    def error(self, message: str) -> None:
        print(f"ERROR: {message}")

    def warning(self, message: str) -> None:
        print(f"WARN: {message}")

    def info(self, message: str) -> None:
        print(message)

    def print_goodbye(self) -> None:
        print("bye")

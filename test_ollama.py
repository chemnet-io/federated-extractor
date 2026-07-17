import os
from typing import Any

from ollama import Client
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule


HOST = "http://141.57.8.18:11434"
MODEL = "gemma4:e4b"
KEEP_ALIVE = "10m"

console = Console()


def create_client() -> Client:
    api_key = os.environ.get("OLLAMA_API_KEY")

    if not api_key:
        console.print(
            "[bold red]Error:[/bold red] "
            "The OLLAMA_API_KEY environment variable is not set."
        )
        console.print(
            'Set it with:\n'
            '[bold]export OLLAMA_API_KEY="your-api-key"[/bold]'
        )
        raise SystemExit(1)

    return Client(
        host=HOST,
        headers={
            "Authorization": f"Bearer {api_key}",
        },
    )


def get_chunk_text(part: Any) -> str:
    try:
        return part.message.content or ""
    except AttributeError:
        return part.get("message", {}).get("content", "")


def main() -> None:
    client = create_client()
    messages: list[dict[str, str]] = []

    console.print(
        Panel.fit(
            f"[bold]Remote Ollama Chat[/bold]\n"
            f"Model: [cyan]{MODEL}[/cyan]\n\n"
            "Commands:\n"
            "  [bold]/clear[/bold] — clear conversation history\n"
            "  [bold]/exit[/bold]  — close the program",
            border_style="cyan",
        )
    )

    while True:
        try:
            prompt = Prompt.ask("\n[bold green]You[/bold green]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Goodbye![/yellow]")
            break

        if not prompt:
            continue

        command = prompt.lower()

        if command in {"/exit", "/quit", "exit", "quit"}:
            console.print("[yellow]Goodbye![/yellow]")
            break

        if command == "/clear":
            messages.clear()
            console.print("[green]Conversation history cleared.[/green]")
            continue

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        full_response = ""
        response_started = False

        status = console.status(
            "[bold cyan]Thinking...[/bold cyan]",
            spinner="dots",
        )
        status.start()

        try:
            stream = client.chat(
                model=MODEL,
                messages=messages,
                stream=True,
                keep_alive=KEEP_ALIVE,
            )

            for part in stream:
                text = get_chunk_text(part)

                # Stop the spinner only when visible text arrives.
                if text and not response_started:
                    status.stop()
                    response_started = True

                full_response += text

        except KeyboardInterrupt:
            status.stop()
            console.print("\n[yellow]Request interrupted.[/yellow]")
            messages.pop()
            continue

        except Exception as error:
            status.stop()
            console.print(
                Panel(
                    str(error),
                    title="[bold red]Request failed[/bold red]",
                    border_style="red",
                )
            )
            messages.pop()
            continue

        finally:
            if not response_started:
                status.stop()

        if not full_response.strip():
            console.print("[yellow]The model returned an empty response.[/yellow]")
            messages.pop()
            continue

        messages.append(
            {
                "role": "assistant",
                "content": full_response,
            }
        )

        console.print()
        console.print(Rule("[bold blue][/bold blue]"))
        console.print(Markdown(full_response))
        console.print(Rule())


if __name__ == "__main__":
    main()

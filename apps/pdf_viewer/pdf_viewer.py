import os
import asyncio
from textual.app import ComposeResult
from textual.widgets import Markdown, Static, LoadingIndicator
from textual.containers import VerticalScroll, Center
from textual import work
import pymupdf4llm

from core.window import Window

class PdfViewer(Window):
    def __init__(self, *args, **kwargs):
        # We assume args[0] is the path to the PDF file if opened via association
        self.file_path = args[0] if args else None
        
        # Set window title
        filename = os.path.basename(self.file_path) if self.file_path else "Untitled PDF"
        super().__init__(f"PDF Viewer - {filename}", "📄")
        
        self.md_content = ""

    def compose(self) -> ComposeResult:
        if not self.file_path:
            yield Static("No PDF file provided.", id="error-msg")
            return

        with VerticalScroll(id="pdf-scroll"):
            yield LoadingIndicator(id="loading")
            yield Markdown("", id="pdf-markdown")

    def on_mount(self) -> None:
        if self.file_path:
            self.load_pdf()

    @work(thread=True)
    def load_pdf(self) -> None:
        try:
            # Convert PDF to Markdown using pymupdf4llm
            # This runs in a worker thread so it doesn't block the UI
            md_text = pymupdf4llm.to_markdown(self.file_path)
            self.app.call_from_thread(self.display_markdown, md_text)
        except Exception as e:
            error_msg = f"# Error reading PDF\n\n`{str(e)}`"
            self.app.call_from_thread(self.display_markdown, error_msg)

    def display_markdown(self, md_text: str) -> None:
        # Hide loading indicator
        loading = self.query_one("#loading")
        loading.display = False
        
        # Update Markdown widget
        md_widget = self.query_one("#pdf-markdown", Markdown)
        md_widget.update(md_text)
        md_widget.focus()

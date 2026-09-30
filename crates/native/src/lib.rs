mod image_engine;
pub use image_engine::ImageEngine;
use pyo3::prelude::*;
use vt100::Parser;

#[pyclass]
struct TerminalEngine {
    parser: Parser,
    cols: u16,
    rows: u16,
}

#[pymethods]
impl TerminalEngine {
    #[new]
    fn new(cols: u16, rows: u16) -> Self {
        TerminalEngine {
            parser: Parser::new(rows, cols, 0),
            cols,
            rows,
        }
    }

    fn process(&mut self, bytes: &[u8]) {
        self.parser.process(bytes);
    }
    fn resize(&mut self, cols: u16, rows: u16) {
        if self.cols == cols && self.rows == rows {
            return;
        }
        self.parser.screen_mut().set_size(rows, cols);
        self.cols = cols;
        self.rows = rows;
    }

    fn cursor_position(&self) -> (u16, u16) {
        self.parser.screen().cursor_position()
    }

    fn hide_cursor(&self) -> bool {
        self.parser.screen().hide_cursor()
    }

    fn render_line(&self, y: u16, has_focus: bool) -> PyResult<Vec<(String, (String, String, bool, bool, bool, bool))>> {
        let mut segments = Vec::new();
        let screen = self.parser.screen();

        if y >= self.rows {
            return Ok(segments);
        }

        let mut current_text = String::new();
        let mut current_style = None;

        let (cursor_row, cursor_col) = screen.cursor_position();
        let hide_cursor = screen.hide_cursor();

        for x in 0..self.cols {
            let (cell_data, style) = if let Some(cell) = screen.cell(y, x) {
                let c = cell.contents();
                let data = if c.is_empty() { " " } else { c };

                let fg_str = match cell.fgcolor() {
                    vt100::Color::Default => "default".to_string(),
                    vt100::Color::Idx(i) => format!("color({})", i),
                    vt100::Color::Rgb(r, g, b) => format!("#{:02x}{:02x}{:02x}", r, g, b),
                };

                let bg_str = match cell.bgcolor() {
                    vt100::Color::Default => "default".to_string(),
                    vt100::Color::Idx(i) => format!("color({})", i),
                    vt100::Color::Rgb(r, g, b) => format!("#{:02x}{:02x}{:02x}", r, g, b),
                };

                let mut inverse = cell.inverse();
                if has_focus && !hide_cursor && cursor_row == y && cursor_col == x {
                    inverse = !inverse;
                }

                (data, (fg_str, bg_str, cell.bold(), cell.italic(), cell.underline(), inverse))
            } else {
                let mut inverse = false;
                if has_focus && !hide_cursor && cursor_row == y && cursor_col == x {
                    inverse = true;
                }
                (" ", ("default".to_string(), "default".to_string(), false, false, false, inverse))
            };

            if current_style.is_none() {
                current_style = Some(style.clone());
                current_text.push_str(cell_data);
            } else if Some(&style) == current_style.as_ref() {
                current_text.push_str(cell_data);
            } else {
                if let Some(s) = current_style {
                    segments.push((current_text, s));
                }
                current_style = Some(style);
                current_text = cell_data.to_string();
            }
        }

        if let Some(s) = current_style {
            segments.push((current_text, s));
        }

        Ok(segments)
    }
}

#[pymodule]
fn rune_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<TerminalEngine>()?;
    m.add_class::<ImageEngine>()?;
    Ok(())
}
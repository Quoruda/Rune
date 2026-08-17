use pyo3::prelude::*;
use std::fmt::Write;

#[inline(always)]
fn is_color_similar(c1: (u8, u8, u8), c2: (u8, u8, u8)) -> bool {
    c1.0.abs_diff(c2.0) <= 3 && c1.1.abs_diff(c2.1) <= 3 && c1.2.abs_diff(c2.2) <= 3
}

#[pyclass]
pub struct ImageEngine {
    width: u16,
    height: u16,
}

#[pymethods]
impl ImageEngine {
    #[new]
    fn new(width: u16, height: u16) -> Self {
        Self { width, height }
    }

    fn render_frame(&self, buffer: &[u8]) -> PyResult<String> {
        let w = self.width as usize;
        let h = self.height as usize;
        
        // Pre-allocate buffer to minimize reallocations
        let mut frame = String::with_capacity(w * h * 15);
        
        // Track previous colors for ANSI escape sequence batching
        let mut last_fg: Option<(u8, u8, u8)> = None;
        let mut last_bg: Option<(u8, u8, u8)> = None;

        for y in (0..h).step_by(2) {
            for x in 0..w {
                let top_idx = (y * w + x) * 3;
                let bot_idx = ((y + 1) * w + x) * 3;

                if bot_idx + 2 >= buffer.len() {
                    break;
                }

                let fg = (buffer[bot_idx], buffer[bot_idx + 1], buffer[bot_idx + 2]);
                let bg = (buffer[top_idx], buffer[top_idx + 1], buffer[top_idx + 2]);

                // Emit ANSI escape codes only when color changes beyond similarity threshold
                let fg_changed = match last_fg {
                    Some(prev) => !is_color_similar(fg, prev),
                    None => true,
                };
                if fg_changed {
                    let _ = write!(frame, "\x1b[38;2;{};{};{}m", fg.0, fg.1, fg.2);
                    last_fg = Some(fg);
                }

                let bg_changed = match last_bg {
                    Some(prev) => !is_color_similar(bg, prev),
                    None => true,
                };
                if bg_changed {
                    let _ = write!(frame, "\x1b[48;2;{};{};{}m", bg.0, bg.1, bg.2);
                    last_bg = Some(bg);
                }
                frame.push('▄');
            }
            frame.push_str("\x1b[0m\n");
            // Reset color cache per row
            last_fg = None;
            last_bg = None;
        }
        Ok(frame)
    }
}
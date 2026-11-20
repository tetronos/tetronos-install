// Rendering. 16 colors only, keyboard only.
use crate::app::{App, FIELDS, Screen, human};
use ratatui::{
    Frame,
    layout::{Constraint, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
};

fn sel(on: bool) -> Style {
    if on { Style::default().fg(Color::Black).bg(Color::Cyan) } else { Style::default() }
}

pub fn draw(f: &mut Frame, a: &App) {
    let area = f.area();
    let [head, body, foot] = Layout::vertical([Constraint::Length(1), Constraint::Min(3), Constraint::Length(2)]).areas(area);
    let title = match a.screen {
        Screen::Disk => "1/5 Disk",
        Screen::User => "2/5 You",
        Screen::Options => "3/5 Options",
        Screen::Confirm => "4/5 Confirm",
        Screen::Install => "5/5 Installing",
        Screen::Done => "Done",
    };
    f.render_widget(
        Paragraph::new(Span::styled(format!(" TetronOS installer  {title}"), Style::default().add_modifier(Modifier::BOLD).fg(Color::Green))),
        head,
    );
    let mut lines: Vec<Line> = vec![];
    match a.screen {
        Screen::Disk => {
            lines.push(Line::from("Select the disk to ERASE and install on:"));
            lines.push(Line::from(""));
            if a.disks.is_empty() {
                lines.push(Line::from("No usable disk found (whole disks of 8 GiB or more, nothing mounted)."));
            }
            for (i, d) in a.disks.iter().enumerate() {
                lines.push(Line::from(Span::styled(
                    format!(" {} {:>8}  {:<5} {} ", d.path, human(d.size), d.bus, d.model),
                    sel(i == a.disk_sel),
                )));
            }
        }
        Screen::User => {
            for (i, name) in FIELDS.iter().enumerate() {
                let v = if i == 1 || i == 2 { "*".repeat(a.fields[i].len()) } else { a.fields[i].clone() };
                let cur = if i == a.field_sel { "_" } else { "" };
                lines.push(Line::from(vec![
                    Span::raw(format!("{name:<16}")),
                    Span::styled(format!(" {v}{cur} "), sel(i == a.field_sel)),
                ]));
            }
        }
        Screen::Options => {
            lines.push(Line::from(vec![
                Span::raw("Autologin on tty1   "),
                Span::styled(if a.autologin { " [x] " } else { " [ ] " }, sel(a.opt_sel == 0)),
                Span::raw("  (space toggles)"),
            ]));
            lines.push(Line::from(vec![
                Span::raw("tetron invite file  "),
                Span::styled(format!(" {}{} ", a.invite, if a.opt_sel == 1 { "_" } else { "" }), sel(a.opt_sel == 1)),
                Span::raw("  (optional path)"),
            ]));
        }
        Screen::Confirm => {
            let target = match &a.image {
                Some((f, s)) => format!("image {f} ({s})"),
                None => a.disks[a.disk_sel].path.clone(),
            };
            lines.push(Line::from(format!("Target     {target}  (everything on it is erased)")));
            lines.push(Line::from(format!("User       {}", a.fields[0])));
            lines.push(Line::from(format!("Hostname   {}", a.fields[3])));
            lines.push(Line::from(format!("Autologin  {}", if a.autologin { "on" } else { "off" })));
            lines.push(Line::from(format!("Invite     {}", if a.invite.is_empty() { "none" } else { &a.invite })));
            lines.push(Line::from(""));
            lines.push(Line::from(vec![
                Span::raw(format!("Type {} to erase and install: ", a.confirm_word())),
                Span::styled(format!(" {}_ ", a.confirm), sel(true)),
            ]));
        }
        Screen::Install => {
            for s in &a.steps {
                lines.push(Line::from(format!("  ok  {s}")));
            }
            lines.push(Line::from(""));
            let room = body.height.saturating_sub(a.steps.len() as u16 + 3) as usize;
            for l in a.log.iter().rev().take(room).collect::<Vec<_>>().into_iter().rev() {
                lines.push(Line::from(Span::styled(l.clone(), Style::default().fg(Color::DarkGray))));
            }
        }
        Screen::Done => {
            match a.status {
                Some(0) => lines.push(Line::from(Span::styled("Installed. Remove the install medium and reboot.", Style::default().fg(Color::Green)))),
                c => {
                    lines.push(Line::from(Span::styled(format!("Install failed (exit {}). Last output:", c.unwrap_or(-1)), Style::default().fg(Color::Red))));
                    for l in a.log.iter().rev().take(12).collect::<Vec<_>>().into_iter().rev() {
                        lines.push(Line::from(l.clone()));
                    }
                }
            }
        }
    }
    f.render_widget(Paragraph::new(lines).block(Block::default().borders(Borders::ALL)).wrap(Wrap { trim: false }), body);
    let keys = match a.screen {
        Screen::Disk => "Up/Down select  Enter next  Esc quit",
        Screen::User => "Tab/Up/Down field  Enter next  Esc back",
        Screen::Options => "Tab switch  Space toggle  Enter next  Esc back",
        Screen::Confirm => "Enter install  Esc back",
        Screen::Install => "Installing, please wait",
        Screen::Done => "r reboot  q quit",
    };
    let err = Span::styled(a.error.clone(), Style::default().fg(Color::Red));
    f.render_widget(Paragraph::new(vec![Line::from(err), Line::from(keys)]), foot);
    
}

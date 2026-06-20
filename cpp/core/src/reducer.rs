//! Pure reducer — `(state, action) -> new_state`.
//!
//! Mirrors the dispatch surface formed by the Python store mixins
//! (`StoreOperationsMixin`, `WorkspaceStoreMixin`) and direct attribute
//! writes. The reducer **never** performs IO and never panics on user
//! input: invalid indices and unknown session IDs are no-ops, matching
//! the Python behaviour (which guards with `if 0 <= idx < len(...)` etc.).

use crate::action::Action;
use crate::state::{AppState, Slot, WorkspaceSession};

/// Scope tag returned alongside the new state so subscribers can filter
/// (matches the Python `emit_state_change(scope)` convention:
/// "viewport", "viewport.split", "document", "workspace", "settings").
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Scope {
    Settings,
    Viewport(&'static str),
    Document,
    Workspace,
    /// Action ignored (e.g. invalid index, no active session).
    NoOp,
}

pub fn reduce(state: &AppState, action: &Action) -> (AppState, Scope) {
    let mut s = state.clone();
    let scope = apply(&mut s, action);
    (s, scope)
}

/// In-place variant — convenient inside the Store where we already own the
/// state buffer.
pub fn apply(state: &mut AppState, action: &Action) -> Scope {
    use Action as A;
    match action {
        // -------------------- Settings --------------------
        A::SetLanguage(v) => {
            state.settings.current_language = v.clone();
            Scope::Settings
        }
        A::SetTheme(v) => {
            state.settings.theme = v.clone();
            Scope::Settings
        }
        A::SetUiMode(v) => {
            state.settings.ui_mode = v.clone();
            Scope::Settings
        }
        A::SetDebugMode(v) => {
            state.settings.debug_mode_enabled = *v;
            Scope::Settings
        }
        A::SetSystemNotifications(v) => {
            state.settings.system_notifications_enabled = *v;
            Scope::Settings
        }
        A::SetAutoCropBlackBorders(v) => {
            state.settings.auto_crop_black_borders = *v;
            Scope::Settings
        }
        A::SetRhiBackend(v) => {
            state.settings.rhi_backend = v.clone();
            Scope::Settings
        }
        A::SetWindowGeometry {
            x,
            y,
            w,
            h,
            maximized,
        } => {
            state.settings.window_x = *x;
            state.settings.window_y = *y;
            state.settings.window_width = *w;
            state.settings.window_height = *h;
            state.settings.window_was_maximized = *maximized;
            Scope::Settings
        }
        A::LoadSettings(new_settings) => {
            state.settings = new_settings.clone();
            Scope::Settings
        }

        // -------------------- View --------------------
        A::SetSplitPosition(v) => {
            let clamped = v.clamp(0.0, 1.0);
            state.viewport.view_state.split_position = clamped;
            Scope::Viewport("split")
        }
        A::SetSplitVisualPosition(v) => {
            state.viewport.view_state.split_position_visual = v.clamp(0.0, 1.0);
            Scope::Viewport("split")
        }
        A::SetSplitOrientation { is_horizontal } => {
            state.viewport.view_state.is_horizontal = *is_horizontal;
            Scope::Viewport("split")
        }
        A::SetDiffMode(v) => {
            state.viewport.view_state.diff_mode = v.clone();
            Scope::Viewport("diff")
        }
        A::SetChannelViewMode(v) => {
            state.viewport.view_state.channel_view_mode = v.clone();
            Scope::Viewport("channel")
        }
        A::SetOverlayEnabled(v) => {
            state.viewport.view_state.overlay_enabled = *v;
            Scope::Viewport("overlay")
        }
        A::SetShowingSingleImageMode(v) => {
            state.viewport.view_state.showing_single_image_mode = *v;
            Scope::Viewport("single_image")
        }

        // -------------------- Geometry --------------------
        A::SetPixmapSize { w, h } => {
            state.viewport.geometry_state.pixmap_width = *w;
            state.viewport.geometry_state.pixmap_height = *h;
            Scope::Viewport("geometry")
        }
        A::SetDisplayRect(r) => {
            state.viewport.geometry_state.image_display_rect_on_label = *r;
            Scope::Viewport("geometry")
        }
        A::SetFixedLabelSize { w, h } => {
            state.viewport.geometry_state.fixed_label_width = *w;
            state.viewport.geometry_state.fixed_label_height = *h;
            Scope::Viewport("geometry")
        }
        A::SetOverlayScreenCenter(p) => {
            state.viewport.geometry_state.active_overlay_screen_center = *p;
            Scope::Viewport("overlay")
        }

        // -------------------- Interaction --------------------
        A::BeginInteractiveSession => {
            let i = &mut state.viewport.interaction_state;
            i.is_interactive_mode = true;
            i.is_user_interacting = true;
            i.interaction_session_id = i.interaction_session_id.wrapping_add(1);
            Scope::Viewport("interaction")
        }
        A::EndInteractiveSession => {
            let i = &mut state.viewport.interaction_state;
            i.is_interactive_mode = false;
            i.is_user_interacting = false;
            i.is_dragging_split_line = false;
            i.is_dragging_overlay_handle = false;
            i.is_dragging_overlay_split = false;
            i.is_dragging_any_slider = false;
            Scope::Viewport("interaction")
        }
        A::SetDraggingSplitLine(v) => {
            state.viewport.interaction_state.is_dragging_split_line = *v;
            Scope::Viewport("interaction")
        }
        A::SetSpaceBarPressed(v) => {
            state.viewport.interaction_state.space_bar_pressed = *v;
            Scope::Viewport("interaction")
        }
        A::KeyPressed(k) => {
            state.viewport.interaction_state.pressed_keys.insert(*k);
            Scope::Viewport("interaction")
        }
        A::KeyReleased(k) => {
            state.viewport.interaction_state.pressed_keys.remove(k);
            Scope::Viewport("interaction")
        }

        // -------------------- Document --------------------
        A::SetCurrentIndex { slot, index } => {
            let doc = &mut state.document;
            let list_len = match slot {
                Slot::Left => doc.image_list1.len(),
                Slot::Right => doc.image_list2.len(),
            };
            if *index < -1 || (*index as i64) >= list_len as i64 {
                return Scope::NoOp;
            }
            match slot {
                Slot::Left => doc.current_index1 = *index,
                Slot::Right => doc.current_index2 = *index,
            }
            Scope::Document
        }
        A::AddImageItem { slot, item } => {
            match slot {
                Slot::Left => state.document.image_list1.push(item.clone()),
                Slot::Right => state.document.image_list2.push(item.clone()),
            }
            Scope::Document
        }
        A::RemoveImageItem { slot, index } => {
            let doc = &mut state.document;
            let (list, current) = match slot {
                Slot::Left => (&mut doc.image_list1, &mut doc.current_index1),
                Slot::Right => (&mut doc.image_list2, &mut doc.current_index2),
            };
            if *index < 0 || (*index as usize) >= list.len() {
                return Scope::NoOp;
            }
            list.remove(*index as usize);
            // Shift the current index the same way the Python code does:
            // clamp into the new range, fall back to -1 when empty.
            if list.is_empty() {
                *current = -1;
            } else if *current >= list.len() as i32 {
                *current = list.len() as i32 - 1;
            }
            Scope::Document
        }
        A::SetActiveImagePath { slot, path } => {
            match slot {
                Slot::Left => state.document.image1_path = path.clone(),
                Slot::Right => state.document.image2_path = path.clone(),
            }
            Scope::Document
        }
        A::BindTextureToSlot { slot, texture } => {
            match slot {
                Slot::Left => state.viewport.image_session.image1 = *texture,
                Slot::Right => state.viewport.image_session.image2 = *texture,
            }
            Scope::Viewport("image_session")
        }

        // -------------------- Workspace --------------------
        A::CreateSession {
            title,
            session_type,
            activate,
        } => {
            let id = next_session_id(state);
            let session = WorkspaceSession {
                id: id.clone(),
                title: title.clone(),
                session_type: session_type.clone(),
                ..Default::default()
            };
            state.workspace.sessions.push(session);
            if *activate || state.workspace.active_session_id.is_none() {
                state.workspace.active_session_id = Some(id);
            }
            Scope::Workspace
        }
        A::SwitchSession(id) => {
            if state.workspace.sessions.iter().any(|s| s.id == *id) {
                if state.workspace.active_session_id.as_deref() == Some(id.as_str()) {
                    Scope::NoOp
                } else {
                    state.workspace.active_session_id = Some(id.clone());
                    Scope::Workspace
                }
            } else {
                Scope::NoOp
            }
        }
        A::CloseSession(id) => {
            // Python invariant: never drop the last session.
            if state.workspace.sessions.len() <= 1 {
                return Scope::NoOp;
            }
            let idx = state.workspace.sessions.iter().position(|s| s.id == *id);
            let Some(idx) = idx else {
                return Scope::NoOp;
            };
            let was_active = state.workspace.active_session_id.as_deref() == Some(id.as_str());
            state.workspace.sessions.remove(idx);
            if was_active {
                let new_idx = idx.min(state.workspace.sessions.len() - 1);
                state.workspace.active_session_id =
                    Some(state.workspace.sessions[new_idx].id.clone());
            }
            Scope::Workspace
        }
        A::RenameSession { id, title } => {
            let normalized = title.trim().to_string();
            if normalized.is_empty() {
                return Scope::NoOp;
            }
            if let Some(s) = state.workspace.sessions.iter_mut().find(|s| s.id == *id) {
                s.title = normalized;
                Scope::Workspace
            } else {
                Scope::NoOp
            }
        }

        // -------------------- Opaque feature blob --------------------
        A::SetFeatureState(v) => {
            state.viewport.view_state.feature_state = v.clone();
            Scope::Viewport("feature_state")
        }
    }
}

fn next_session_id(state: &mut AppState) -> String {
    state.workspace.next_session_counter += 1;
    format!("session_{}", state.workspace.next_session_counter)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::{ImageItem, Slot};

    #[test]
    fn settings_actions_emit_settings_scope() {
        let mut s = AppState::default();
        assert_eq!(
            apply(&mut s, &Action::SetTheme("dark".into())),
            Scope::Settings
        );
        assert_eq!(s.settings.theme, "dark");
        assert_eq!(
            apply(&mut s, &Action::SetLanguage("ru".into())),
            Scope::Settings
        );
        assert_eq!(s.settings.current_language, "ru");
    }

    #[test]
    fn split_position_is_clamped() {
        let mut s = AppState::default();
        apply(&mut s, &Action::SetSplitPosition(1.7));
        assert_eq!(s.viewport.view_state.split_position, 1.0);
        apply(&mut s, &Action::SetSplitPosition(-0.5));
        assert_eq!(s.viewport.view_state.split_position, 0.0);
        apply(&mut s, &Action::SetSplitPosition(0.42));
        assert!((s.viewport.view_state.split_position - 0.42).abs() < 1e-6);
    }

    #[test]
    fn interactive_session_lifecycle() {
        let mut s = AppState::default();
        apply(&mut s, &Action::BeginInteractiveSession);
        assert!(s.viewport.interaction_state.is_interactive_mode);
        assert_eq!(s.viewport.interaction_state.interaction_session_id, 1);
        apply(&mut s, &Action::SetDraggingSplitLine(true));
        assert!(s.viewport.interaction_state.is_dragging_split_line);
        apply(&mut s, &Action::EndInteractiveSession);
        assert!(!s.viewport.interaction_state.is_interactive_mode);
        assert!(!s.viewport.interaction_state.is_dragging_split_line);
    }

    #[test]
    fn key_set_grows_and_shrinks() {
        let mut s = AppState::default();
        apply(&mut s, &Action::KeyPressed(16777234)); // arbitrary Qt key code
        apply(&mut s, &Action::KeyPressed(16777236));
        assert_eq!(s.viewport.interaction_state.pressed_keys.len(), 2);
        apply(&mut s, &Action::KeyReleased(16777234));
        assert_eq!(s.viewport.interaction_state.pressed_keys.len(), 1);
        apply(&mut s, &Action::KeyReleased(99999)); // never pressed — no-op-ish
        assert_eq!(s.viewport.interaction_state.pressed_keys.len(), 1);
    }

    #[test]
    fn document_add_remove_keeps_index_in_range() {
        let mut s = AppState::default();
        apply(
            &mut s,
            &Action::AddImageItem {
                slot: Slot::Left,
                item: ImageItem {
                    path: "a.png".into(),
                    ..Default::default()
                },
            },
        );
        apply(
            &mut s,
            &Action::AddImageItem {
                slot: Slot::Left,
                item: ImageItem {
                    path: "b.png".into(),
                    ..Default::default()
                },
            },
        );
        apply(
            &mut s,
            &Action::SetCurrentIndex {
                slot: Slot::Left,
                index: 1,
            },
        );
        assert_eq!(s.document.current_index1, 1);

        apply(
            &mut s,
            &Action::RemoveImageItem {
                slot: Slot::Left,
                index: 1,
            },
        );
        // Index was 1, list shrunk to 1 entry → clamp to last.
        assert_eq!(s.document.current_index1, 0);
        apply(
            &mut s,
            &Action::RemoveImageItem {
                slot: Slot::Left,
                index: 0,
            },
        );
        // Empty list → -1.
        assert_eq!(s.document.current_index1, -1);
    }

    #[test]
    fn invalid_set_current_index_is_noop() {
        let mut s = AppState::default();
        let before = s.clone();
        let scope = apply(
            &mut s,
            &Action::SetCurrentIndex {
                slot: Slot::Left,
                index: 99,
            },
        );
        assert_eq!(scope, Scope::NoOp);
        assert_eq!(s, before);
    }

    #[test]
    fn workspace_session_lifecycle() {
        let mut s = AppState::default();
        apply(
            &mut s,
            &Action::CreateSession {
                title: "First".into(),
                session_type: "image_compare".into(),
                activate: true,
            },
        );
        apply(
            &mut s,
            &Action::CreateSession {
                title: "Second".into(),
                session_type: "image_compare".into(),
                activate: false,
            },
        );
        assert_eq!(s.workspace.sessions.len(), 2);
        assert_eq!(s.workspace.active_session_id, Some("session_1".into()));

        let scope = apply(&mut s, &Action::SwitchSession("session_2".into()));
        assert_eq!(scope, Scope::Workspace);
        assert_eq!(s.workspace.active_session_id, Some("session_2".into()));

        // Same id → no-op.
        let scope = apply(&mut s, &Action::SwitchSession("session_2".into()));
        assert_eq!(scope, Scope::NoOp);

        // Cannot close the last session.
        apply(&mut s, &Action::CloseSession("session_1".into()));
        assert_eq!(s.workspace.sessions.len(), 1);
        let scope = apply(&mut s, &Action::CloseSession("session_2".into()));
        assert_eq!(scope, Scope::NoOp);
        assert_eq!(s.workspace.sessions.len(), 1);

        // Rename — empty/whitespace ignored.
        let scope = apply(
            &mut s,
            &Action::RenameSession {
                id: "session_2".into(),
                title: "   ".into(),
            },
        );
        assert_eq!(scope, Scope::NoOp);
        let scope = apply(
            &mut s,
            &Action::RenameSession {
                id: "session_2".into(),
                title: " Renamed ".into(),
            },
        );
        assert_eq!(scope, Scope::Workspace);
        assert_eq!(s.workspace.sessions[0].title, "Renamed");
    }

    #[test]
    fn reduce_returns_new_state_unchanged_original() {
        let original = AppState::default();
        let (next, scope) = reduce(&original, &Action::SetTheme("light".into()));
        assert_eq!(scope, Scope::Settings);
        assert_eq!(original.settings.theme, "auto");
        assert_eq!(next.settings.theme, "light");
    }
}

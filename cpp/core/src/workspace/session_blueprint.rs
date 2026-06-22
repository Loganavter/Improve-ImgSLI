//! Serializable workspace-session blueprint defaults.
//!
//! Mirrors `src/core/session_blueprints.py` and
//! `WorkspaceStoreMixin::_apply_session_blueprint`. Python factories are
//! intentionally represented by their already-materialized JSON defaults:
//! executable Python callables cannot cross the standalone C++/Rust boundary.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::core::state::WorkspaceSession;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct SessionSlotBlueprint {
    pub name: String,
    pub default: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct SessionResourceBlueprint {
    pub namespace: String,
    pub entries: Map<String, Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct SessionBlueprint {
    pub session_type: String,
    pub plugin_name: String,
    pub title: Option<String>,
    pub state_slots: Vec<SessionSlotBlueprint>,
    pub resource_namespaces: Vec<SessionResourceBlueprint>,
    pub metadata_defaults: Map<String, Value>,
}

impl SessionBlueprint {
    pub fn resolved_title(&self) -> Option<&str> {
        self.title
            .as_deref()
            .map(str::trim)
            .filter(|title| !title.is_empty())
    }

    pub fn apply_to(&self, session: &mut WorkspaceSession) {
        for slot in &self.state_slots {
            session
                .state_slots
                .insert(slot.name.clone(), slot.default.clone());
        }
        for resource in &self.resource_namespaces {
            session
                .resources
                .insert(resource.namespace.clone(), resource.entries.clone());
        }
        session.metadata.extend(self.metadata_defaults.clone());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn python_shape_deserializes_and_applies_defaults() {
        let blueprint: SessionBlueprint = serde_json::from_value(json!({
            "session_type": "video_compare",
            "plugin_name": "video_editor",
            "title": " Video Compare ",
            "state_slots": [
                {"name": "video.timeline", "default": {"position_ms": 0}},
                {"name": "video.selection", "default": null}
            ],
            "resource_namespaces": [
                {"namespace": "video", "entries": {"fps": 60}},
                {"namespace": "thumbnails"}
            ],
            "metadata_defaults": {"plugin": "video_editor"}
        }))
        .unwrap();

        let mut session = WorkspaceSession::default();
        blueprint.apply_to(&mut session);

        assert_eq!(blueprint.resolved_title(), Some("Video Compare"));
        assert_eq!(
            session.state_slots["video.timeline"],
            json!({"position_ms": 0})
        );
        assert_eq!(session.state_slots["video.selection"], Value::Null);
        assert_eq!(session.resources["video"]["fps"], json!(60));
        assert!(session.resources["thumbnails"].is_empty());
        assert_eq!(session.metadata["plugin"], json!("video_editor"));
    }

    #[test]
    fn applying_blueprint_replaces_named_defaults_like_python() {
        let mut session = WorkspaceSession::default();
        session.state_slots.insert("slot".into(), json!("old"));
        session
            .resources
            .insert("cache".into(), Map::from_iter([("old".into(), json!(1))]));
        session.metadata.insert("keep".into(), json!(true));

        SessionBlueprint {
            state_slots: vec![SessionSlotBlueprint {
                name: "slot".into(),
                default: json!("new"),
            }],
            resource_namespaces: vec![SessionResourceBlueprint {
                namespace: "cache".into(),
                entries: Map::from_iter([("fresh".into(), json!(2))]),
            }],
            metadata_defaults: Map::from_iter([("plugin".into(), json!("comparison"))]),
            ..Default::default()
        }
        .apply_to(&mut session);

        assert_eq!(session.state_slots["slot"], json!("new"));
        assert_eq!(session.resources["cache"]["fresh"], json!(2));
        assert!(!session.resources["cache"].contains_key("old"));
        assert_eq!(session.metadata["keep"], json!(true));
    }
}

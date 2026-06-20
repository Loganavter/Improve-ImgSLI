//! Semantic canvas stacking policy.
//!
//! This is the Rust counterpart of
//! `src/ui/canvas_infra/scene/stacking_policy.py`. C++ passes expose only a
//! semantic role; the registry asks this module for the concrete phase and
//! priority.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(i32)]
pub enum StackRole {
    UnderlaySplit = 10,
    ImageOverlayFrame = 15,
    ImageOverlayContent = 20,
    AnnotationRing = 30,
    AnnotationBorder = 35,
    AnnotationGuide = 40,
    HudLabel = 50,
    TransientPreview = 55,
    InteractionHandle = 60,
    DebugVis = 70,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StackOrder {
    pub phase: i32,
    pub priority: i32,
}

pub fn resolve(role: i32) -> StackOrder {
    match role {
        x if x == StackRole::UnderlaySplit as i32 => StackOrder {
            phase: 10,
            priority: 10,
        },
        x if x == StackRole::AnnotationGuide as i32 => StackOrder {
            phase: 20,
            priority: 60,
        },
        x if x == StackRole::AnnotationRing as i32 => StackOrder {
            phase: 20,
            priority: 70,
        },
        x if x == StackRole::ImageOverlayFrame as i32 => StackOrder {
            phase: 20,
            priority: 90,
        },
        x if x == StackRole::ImageOverlayContent as i32 => StackOrder {
            phase: 20,
            priority: 100,
        },
        x if x == StackRole::AnnotationBorder as i32 => StackOrder {
            phase: 30,
            priority: 15,
        },
        x if x == StackRole::InteractionHandle as i32 => StackOrder {
            phase: 30,
            priority: 50,
        },
        x if x == StackRole::TransientPreview as i32 => StackOrder {
            phase: 40,
            priority: 50,
        },
        x if x == StackRole::HudLabel as i32 => StackOrder {
            phase: 40,
            priority: 100,
        },
        x if x == StackRole::DebugVis as i32 => StackOrder {
            phase: 50,
            priority: 10,
        },
        _ => StackOrder {
            phase: 30,
            priority: 100,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roles_match_python_policy_order() {
        assert!(
            resolve(StackRole::UnderlaySplit as i32).phase
                < resolve(StackRole::ImageOverlayContent as i32).phase
        );
        assert!(
            resolve(StackRole::AnnotationGuide as i32).priority
                < resolve(StackRole::ImageOverlayContent as i32).priority
        );
        assert!(
            resolve(StackRole::HudLabel as i32).phase
                > resolve(StackRole::AnnotationBorder as i32).phase
        );
    }
}

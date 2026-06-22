//! Translation loader.
//!
//! Mirrors `sli_ui_toolkit.i18n.TranslationManager` enough that the C++ Qt
//! side can keep using the existing JSON dictionaries under
//! `src/resources/i18n/<lang>/...` without converting them to `.ts`. Keys
//! are nested dotted paths, e.g. `settings.appearance`.
//!
//! Lookup falls back to English when a key is missing in the requested
//! language, and returns the key itself when nothing matches (same as the
//! Python helper).

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde_json::Value;

#[derive(Debug, Default)]
struct LanguagePack {
    entries: HashMap<String, String>,
}

#[derive(Debug, Default)]
pub struct TranslationStore {
    root: Option<PathBuf>,
    current: String,
    requested: LanguagePack,
    fallback: LanguagePack,
}

impl TranslationStore {
    pub fn new() -> Self {
        Self {
            root: None,
            current: "en".into(),
            requested: LanguagePack::default(),
            fallback: LanguagePack::default(),
        }
    }

    pub fn set_root(&mut self, root: impl Into<PathBuf>) {
        self.root = Some(root.into());
        self.reload();
    }

    pub fn set_language(&mut self, lang: &str) {
        if lang == self.current && !self.requested.entries.is_empty() {
            return;
        }
        self.current = lang.to_string();
        self.reload();
    }

    pub fn current_language(&self) -> &str {
        &self.current
    }

    pub fn translate<'a>(&'a self, key: &'a str) -> &'a str {
        if let Some(s) = self.requested.entries.get(key) {
            return s.as_str();
        }
        if let Some(s) = self.fallback.entries.get(key) {
            return s.as_str();
        }
        key
    }

    fn reload(&mut self) {
        let Some(root) = self.root.clone() else {
            return;
        };
        self.fallback = load_language(&root, "en");
        if self.current == "en" {
            self.requested = LanguagePack::default();
        } else {
            self.requested = load_language(&root, &self.current);
        }
    }
}

fn load_language(root: &Path, lang: &str) -> LanguagePack {
    let lang_dir = root.join(lang);
    let mut entries = HashMap::new();
    walk_json(&lang_dir, &mut |json| {
        flatten(&json, String::new(), &mut entries);
    });
    LanguagePack { entries }
}

fn walk_json(dir: &Path, sink: &mut impl FnMut(Value)) {
    let Ok(read) = fs::read_dir(dir) else {
        return;
    };
    let mut paths: Vec<PathBuf> = read.filter_map(|e| e.ok().map(|e| e.path())).collect();
    paths.sort();
    for path in paths {
        if path.is_dir() {
            walk_json(&path, sink);
            continue;
        }
        if path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let Ok(text) = fs::read_to_string(&path) else {
            continue;
        };
        if let Ok(json) = serde_json::from_str::<Value>(&text) {
            sink(json);
        }
    }
}

fn flatten(value: &Value, prefix: String, sink: &mut HashMap<String, String>) {
    match value {
        Value::Object(map) => {
            for (k, v) in map {
                let next = if prefix.is_empty() {
                    k.clone()
                } else {
                    format!("{prefix}.{k}")
                };
                flatten(v, next, sink);
            }
        }
        Value::String(s) => {
            sink.insert(prefix, s.clone());
        }
        Value::Number(n) => {
            sink.insert(prefix, n.to_string());
        }
        Value::Bool(b) => {
            sink.insert(prefix, b.to_string());
        }
        // Null / arrays are not meaningful translation values; ignore.
        _ => {}
    }
}

// Process-wide singleton — C++ holds no state, the Rust core owns it.
static GLOBAL: Mutex<Option<TranslationStore>> = Mutex::new(None);

fn with_store<R>(f: impl FnOnce(&mut TranslationStore) -> R) -> R {
    let mut guard = GLOBAL.lock().expect("translation store poisoned");
    if guard.is_none() {
        *guard = Some(TranslationStore::new());
    }
    f(guard.as_mut().expect("translation store"))
}

pub fn init(root: &str) {
    with_store(|s| s.set_root(root));
}

pub fn set_language(lang: &str) {
    with_store(|s| s.set_language(lang));
}

pub fn translate(key: &str) -> String {
    with_store(|s| s.translate(key).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Write;

    fn write(path: &Path, body: &str) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        let mut f = fs::File::create(path).unwrap();
        f.write_all(body.as_bytes()).unwrap();
    }

    #[test]
    fn flatten_nested_object_to_dot_paths() {
        let v: Value = serde_json::from_str(r#"{"a":{"b":"x","c":"y"},"d":"z"}"#).unwrap();
        let mut out = HashMap::new();
        flatten(&v, String::new(), &mut out);
        assert_eq!(out.get("a.b"), Some(&"x".to_string()));
        assert_eq!(out.get("a.c"), Some(&"y".to_string()));
        assert_eq!(out.get("d"), Some(&"z".to_string()));
    }

    #[test]
    fn translate_returns_key_when_missing() {
        let mut s = TranslationStore::new();
        assert_eq!(s.translate("settings.foo"), "settings.foo");
        s.set_language("fr");
        assert_eq!(s.translate("settings.foo"), "settings.foo");
    }

    #[test]
    fn translate_falls_back_to_en() {
        let dir = std::env::temp_dir().join(format!(
            "imgsli-i18n-test-{}-{}",
            std::process::id(),
            line!()
        ));
        write(
            &dir.join("en/settings/general.json"),
            r#"{"settings":{"theme":"Theme"}}"#,
        );
        write(
            &dir.join("ru/settings/general.json"),
            r#"{"settings":{"theme":"Тема"}}"#,
        );
        write(
            &dir.join("ru/extras/help.json"),
            r#"{"help":{"title":"Помощь"}}"#,
        );

        let mut s = TranslationStore::new();
        s.set_root(&dir);
        s.set_language("ru");

        assert_eq!(s.translate("settings.theme"), "Тема");
        assert_eq!(s.translate("help.title"), "Помощь");
        // missing in ru, should fall back to en value if present
        s.set_language("en");
        assert_eq!(s.translate("settings.theme"), "Theme");
        // truly missing -> key
        assert_eq!(s.translate("nothing.here"), "nothing.here");

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn deep_merge_across_files() {
        let dir = std::env::temp_dir().join(format!(
            "imgsli-i18n-merge-{}-{}",
            std::process::id(),
            line!()
        ));
        write(&dir.join("en/a.json"), r#"{"x":{"a":"1"}}"#);
        write(&dir.join("en/b.json"), r#"{"x":{"b":"2"}}"#);

        let pack = load_language(&dir, "en");
        assert_eq!(pack.entries.get("x.a"), Some(&"1".to_string()));
        assert_eq!(pack.entries.get("x.b"), Some(&"2".to_string()));

        let _ = fs::remove_dir_all(&dir);
    }
}

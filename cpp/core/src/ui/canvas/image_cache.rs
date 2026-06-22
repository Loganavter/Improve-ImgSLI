//! LRU image-pair cache.
//!
//! Replaces the `OrderedDict`-backed cache in
//! `src/core/store_viewport.py::RenderCacheState.unified_image_cache` and the
//! presenter-coupled helpers in
//! `src/ui/presenters/image_canvas/background_parts/image_cache.py`.
//!
//! Storage shape:
//!
//! * Key: `(path1, path2, mtime1_ns, mtime2_ns, resolution_limit)`.
//!   Including `mtime` makes the cache safe across file edits without
//!   re-reading content.
//! * Value: per-side cached image (`width`, `height`, opaque bytes — the
//!   pixel format is the caller's contract; the cache is dumb storage).
//! * Eviction: oldest access first, capacity in entries.
//!
//! Pixel ownership stays in C++ once the cutover happens — for the Rust
//! parallel-validation phase we store actual bytes here.

use std::collections::HashMap;

/// One entry's value: a cached image pair plus the dimensions both images
/// agreed on (they're resized in lockstep by `resize_images_processor` in the
/// Python pipeline).
#[derive(Debug, Clone, PartialEq)]
pub struct CachedPair {
    pub width: u32,
    pub height: u32,
    pub bytes_left: Vec<u8>,
    pub bytes_right: Vec<u8>,
}

#[derive(Debug, Clone, Hash, PartialEq, Eq)]
pub struct PairKey {
    pub path1: String,
    pub path2: String,
    pub mtime1_ns: i128,
    pub mtime2_ns: i128,
    pub resolution_limit: i32,
}

/// Simple LRU using `HashMap<K, (V, u64)>` + monotonic counter. Adequate for
/// the cache sizes we expect (≤ 16 entries) and far easier to audit than a
/// crate-backed implementation. Swap for `lru::LruCache` later if needed.
pub struct ImagePairCache {
    capacity: usize,
    counter: u64,
    map: HashMap<PairKey, (CachedPair, u64)>,
}

impl ImagePairCache {
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "ImagePairCache capacity must be > 0");
        Self {
            capacity,
            counter: 0,
            map: HashMap::with_capacity(capacity),
        }
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    /// Look up by key, bumping the entry's recency on hit. Returns a clone of
    /// the cached pair so callers can treat the cache as immutable storage.
    pub fn get(&mut self, key: &PairKey) -> Option<CachedPair> {
        let next = self.bump();
        let entry = self.map.get_mut(key)?;
        entry.1 = next;
        Some(entry.0.clone())
    }

    /// Insert or replace. If the cache is full, the least-recently-used
    /// entry is evicted.
    pub fn put(&mut self, key: PairKey, value: CachedPair) {
        let next = self.bump();
        if let Some(entry) = self.map.get_mut(&key) {
            *entry = (value, next);
            return;
        }
        if self.map.len() >= self.capacity {
            self.evict_lru();
        }
        self.map.insert(key, (value, next));
    }

    pub fn clear(&mut self) {
        self.map.clear();
        self.counter = 0;
    }

    fn bump(&mut self) -> u64 {
        self.counter = self.counter.wrapping_add(1);
        self.counter
    }

    fn evict_lru(&mut self) {
        let Some(lru_key) = self
            .map
            .iter()
            .min_by_key(|(_, (_, age))| *age)
            .map(|(k, _)| k.clone())
        else {
            return;
        };
        self.map.remove(&lru_key);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(p1: &str, p2: &str) -> PairKey {
        PairKey {
            path1: p1.into(),
            path2: p2.into(),
            mtime1_ns: 0,
            mtime2_ns: 0,
            resolution_limit: 0,
        }
    }

    fn pair(seed: u8) -> CachedPair {
        CachedPair {
            width: 1,
            height: 1,
            bytes_left: vec![seed],
            bytes_right: vec![seed.wrapping_add(1)],
        }
    }

    #[test]
    fn hit_miss_basic() {
        let mut c = ImagePairCache::new(4);
        let k = key("a.png", "b.png");
        assert!(c.get(&k).is_none());
        c.put(k.clone(), pair(1));
        assert_eq!(c.get(&k).map(|p| p.bytes_left), Some(vec![1]));
    }

    #[test]
    fn mtime_isolates_entries() {
        let mut c = ImagePairCache::new(4);
        let k1 = PairKey {
            mtime1_ns: 1000,
            ..key("a", "b")
        };
        let k2 = PairKey {
            mtime1_ns: 2000,
            ..key("a", "b")
        };
        c.put(k1.clone(), pair(1));
        c.put(k2.clone(), pair(2));
        assert_eq!(c.get(&k1).unwrap().bytes_left, vec![1]);
        assert_eq!(c.get(&k2).unwrap().bytes_left, vec![2]);
    }

    #[test]
    fn lru_eviction_when_full() {
        let mut c = ImagePairCache::new(2);
        c.put(key("a", "b"), pair(1));
        c.put(key("c", "d"), pair(2));
        // Touch ("a","b") so ("c","d") is the LRU.
        let _ = c.get(&key("a", "b"));
        c.put(key("e", "f"), pair(3));
        assert!(
            c.get(&key("c", "d")).is_none(),
            "LRU should have been evicted"
        );
        assert!(c.get(&key("a", "b")).is_some());
        assert!(c.get(&key("e", "f")).is_some());
        assert_eq!(c.len(), 2);
    }

    #[test]
    fn replace_does_not_grow_or_evict() {
        let mut c = ImagePairCache::new(2);
        c.put(key("a", "b"), pair(1));
        c.put(key("c", "d"), pair(2));
        c.put(key("a", "b"), pair(9));
        assert_eq!(c.len(), 2);
        assert_eq!(c.get(&key("a", "b")).unwrap().bytes_left, vec![9]);
        assert!(c.get(&key("c", "d")).is_some());
    }

    #[test]
    fn clear_resets() {
        let mut c = ImagePairCache::new(2);
        c.put(key("a", "b"), pair(1));
        c.clear();
        assert!(c.is_empty());
    }
}

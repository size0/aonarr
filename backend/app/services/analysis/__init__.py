"""拆书引擎 (Track C) — 五步管线 + 文风指纹"""

from app.services.analysis.importer import import_file, ImportResult
from app.services.analysis.chapter_splitter import split_chapters, SplitResult, Chapter
from app.services.analysis.entity_scanner import scan_entities, confirm_entities_with_llm, ScanResult, Entity
from app.services.analysis.chapter_extractor import extract_chapter, extract_all_chapters, ChapterAnalysis
from app.services.analysis.aggregator import aggregate, deep_aggregate, AggregationResult
from app.services.analysis.style_fingerprint import analyze_style, analyze_style_with_llm, StyleFingerprint

__all__ = [
    "import_file", "ImportResult",
    "split_chapters", "SplitResult", "Chapter",
    "scan_entities", "confirm_entities_with_llm", "ScanResult", "Entity",
    "extract_chapter", "extract_all_chapters", "ChapterAnalysis",
    "aggregate", "deep_aggregate", "AggregationResult",
    "analyze_style", "analyze_style_with_llm", "StyleFingerprint",
]

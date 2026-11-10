"""Stable interfaces for replaceable Knowledge infrastructure."""

from knowledge.ports.chunking import ChunkResult, DocumentChunkerPort
from knowledge.ports.documents import DocumentParserPort
from knowledge.ports.indexing import IndexBackendPort
from knowledge.ports.runs import RunExecutorPort
from knowledge.ports.sources import SourceAssetRef, SourceConnectorPort
from knowledge.ports.storage import AssetAccessContext, AssetEntry, AssetReference, AssetStoreError, AssetStorePort, ArtifactStorePort

__all__ = [
    "ArtifactStorePort",
    "AssetAccessContext",
    "AssetEntry",
    "AssetReference",
    "AssetStoreError",
    "AssetStorePort",
    "ChunkResult",
    "DocumentChunkerPort",
    "DocumentParserPort",
    "IndexBackendPort",
    "RunExecutorPort",
    "SourceConnectorPort",
    "SourceAssetRef",
]

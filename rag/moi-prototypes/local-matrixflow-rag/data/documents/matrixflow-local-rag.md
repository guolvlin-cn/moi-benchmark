# MatrixFlow product RAG

MatrixFlow's product RAG retrieval is implemented by `SearchRAGChunks`.
It searches product-compatible vector tables in MatrixOne through full-text and
vector routes, merges the candidates, and expands the winning evidence chunks.

The old local smoke POC stored documents in SQLite and exposed `POST /ingest`.
That POC is not the MatrixFlow product retrieval implementation.

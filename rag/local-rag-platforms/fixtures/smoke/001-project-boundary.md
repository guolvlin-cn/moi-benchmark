# Benchmark boundary

The RAG benchmark keeps the service under test on the local Colima machine. MatrixOrigin TaaS is allowed only as the external model and embedding endpoint. A successful local deployment therefore means the RAG product, its database, parser, and index service are local; it does not mean the model call is offline.

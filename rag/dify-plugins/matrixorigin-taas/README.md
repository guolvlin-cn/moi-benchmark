# MatrixOrigin TaaS Provider for Dify

This private Dify model-provider plugin connects Dify to MatrixOrigin TaaS.

Supported predefined models:

- `bge-m3` — text embedding
- `qwen3-vl-embedding` — text and image embedding
- `qwen3-rerank` — text rerank
- `qwen3-vl-rerank` — text and image rerank

## Install

Upload `matrixorigin-taas.difypkg` from **Plugins → Install Plugin → Via Local
File**. Then open **Settings → Model Provider → MatrixOrigin TaaS**, enter your
TaaS API key, and keep the default base URL unless you use another gateway.

The package never contains an API key. Credentials are stored by Dify after
installation.

## Why a dedicated provider is needed

The generic OpenAI-compatible plugin sends multimodal embedding input through
the vLLM `messages` extension. TaaS expects OpenAI content parts under
`input[].content` instead. This plugin performs that translation and invokes
`qwen3-vl-embedding` one item at a time to preserve TaaS response cardinality.

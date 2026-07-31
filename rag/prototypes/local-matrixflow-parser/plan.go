package localparser

import "strings"

type ParsePlan struct {
	DirectV2     bool                 `json:"direct_v2"`
	Conformance  Conformance          `json:"conformance"`
	Dependencies []ExternalDependency `json:"external_dependencies,omitempty"`
}

// PlanFor mirrors the standard_rag parser boundary. Backends intentionally
// remain unconfigured in localClientProvider; this plan makes every missing
// product service explicit instead of silently substituting another parser.
func PlanFor(fileType, profile string, additional map[string]any) ParsePlan {
	fileType = normalizeFileType(fileType)
	if profile == ProfileV3Native {
		return ParsePlan{Conformance: Conformance{
			Profile: profile, WebEquivalent: false, Route: "moi:parse/v3/native",
			Reason: "explicit local-only parser profile; the web standard_rag node is V2",
		}}
	}

	plan := ParsePlan{Conformance: Conformance{
		Profile: profile, WebEquivalent: true, Route: "moi:document.parse/v2",
	}}
	add := func(name, usedFor string, required bool) {
		plan.Dependencies = append(plan.Dependencies, ExternalDependency{
			Name: name, Required: required, Status: "not_configured", UsedFor: usedFor,
		})
	}
	switch fileType {
	case "pdf":
		plan.DirectV2 = true
		add("mineru", "PDF layout/OCR parsing", true)
		add("vlm", "conditional OCR/caption for image blocks", false)
	case "doc", "docx", "ppt", "pptx":
		plan.DirectV2 = true
		add("document-converter", "Office to PDF conversion", true)
		add("mineru", "converted PDF layout/OCR parsing", true)
		add("vlm", "conditional OCR/caption for image blocks", false)
	case "xls", "xlsx":
		plan.DirectV2 = true
		add("openxml", "spreadsheet parsing", true)
	case "png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff", "svg":
		plan.Conformance.WebEquivalent = false
		plan.Conformance.Route = "legacy-image-parser"
		plan.Conformance.Reason = "the standalone local adapter does not configure the web image parser"
		add("vlm", "image OCR and caption", true)
	default:
		// In standard_rag these formats are handled by RichConverter's legacy
		// pre-dispatch. That helper is not exported, so the standalone adapter
		// uses the product V3 native block source and records the deviation.
		plan.Conformance.WebEquivalent = false
		plan.Conformance.Route = "legacy-local-format-adapter/v3-native"
		plan.Conformance.Reason = "web V2 legacy pre-dispatch is package-private; product V3 native source is used locally"
	}
	if boolOption(additional, "enable_paddle_preprocess") {
		add("paddle", "optional table-region detection and PDF whitening", false)
	}
	if boolOption(additional, "enable_vlm_title_detection") ||
		boolOption(additional, "enable_vlm_header_footer_detection") ||
		boolOption(additional, "enable_formula_repair") ||
		boolOption(additional, "cast_table_as_image") {
		add("vlm", "optional V2 visual enrichment", false)
	}
	return plan
}

func boolOption(values map[string]any, key string) bool {
	value, ok := values[key]
	if !ok {
		return false
	}
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		return strings.EqualFold(strings.TrimSpace(typed), "true")
	default:
		return false
	}
}

.PHONY: test validate demo archive

test:
	cd reference && python3 -m unittest discover -s tests -v

validate:
	./scripts/validate-bundle.sh

demo:
	./scripts/demo-hook-roundtrip.sh

archive:
	cd .. && zip -qr volatile-context-implementer-bundle.zip volatile-context-implementer-bundle

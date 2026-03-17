# Claude Code Widget – dev helpers
SCHEME  = ClaudeWidget
PROJ    = ClaudeWidget.xcodeproj
DEST    = $(HOME)/Applications/ClaudeWidget.app

.PHONY: build dev clean reset icon

## Build and install (fastest iteration loop)
build:
	@echo "→ Killing running app..."
	@pkill -x ClaudeWidget 2>/dev/null || true
	@sleep 0.3
	@echo "→ Building..."
	@xcodebuild -project $(PROJ) -scheme $(SCHEME) -configuration Debug \
		-destination 'platform=macOS' build 2>&1 \
		| grep -E "error:|warning:|Build succeeded|Build FAILED|▸" || true

dev: build
	@echo "→ Launching app..."
	@open $(DEST) 2>/dev/null || true

## Remove widget + app so macOS re-registers it (needed after structural changes)
reset:
	@pkill -x ClaudeWidget 2>/dev/null || true
	@sleep 0.2
	@rm -rf "$(DEST)"
	@pkill -x WidgetKitService 2>/dev/null || true
	@echo "✓ Reset done. Build and re-add widget from desktop."

clean:
	@xcodebuild -project $(PROJ) -scheme $(SCHEME) clean -quiet

icon:
	@python3 make_icon.py

#!/bin/bash
cd hiddify-panel/src
git commit --amend -m "Refactor bulk_register to accept models instead of dict" \
-m "Updated bulk_register methods and add_or_update to safely process and store typed dataclass DTOs from cross-node payloads. Included backward compatibility shims for JSON backup callers and retained partial updates."

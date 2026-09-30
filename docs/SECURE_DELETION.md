# Secure Deletion & Orphaned Storage Cleanup V1

This layer ensures that deleting a database row cannot leave DOCX bytes behind in Storage.

Document deletion now verifies ownership, combines recorded storage paths with every object discovered under the owned document prefix, marks the document as deleting, removes Storage objects first in bounded batches, marks delete_failed if Storage removal fails, and only then deletes the database document.

Account deletion removes every document, performs a final owner-level Storage sweep for historical or unreferenced objects, and only then deletes the Auth user. The existing ON DELETE RESTRICT foreign key remains an additional guard.

DEL-001 through DEL-012 protect recursive discovery, batching, owner scoping, orphan discovery, Storage-before-DB ordering, recoverable delete failure, owner-level cleanup, Storage-before-Auth ordering, auditable deletion counts, and the account foreign-key guard.

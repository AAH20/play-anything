// Run once against the configured database using an account with schema privileges.
// The application's Neo4j account needs read/write permissions for these labels.
// Unique keys are required: they protect the fixed workspace and make MERGE
// idempotent when identical graph revisions are saved concurrently.
CREATE CONSTRAINT graph_workspace_namespace IF NOT EXISTS
FOR (workspace:GraphWorkspace)
REQUIRE workspace.namespace IS UNIQUE;

CREATE CONSTRAINT graph_revision_key IF NOT EXISTS
FOR (revision:GraphRevision)
REQUIRE (revision.namespace, revision.revision) IS UNIQUE;

CREATE CONSTRAINT code_node_key IF NOT EXISTS
FOR (node:CodeNode)
REQUIRE (node.namespace, node.revision, node.id) IS UNIQUE;

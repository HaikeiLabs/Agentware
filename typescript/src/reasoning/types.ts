// Versioned context-tree contract for normalized reasoning.
// Mirrors go/reasoning/types.go and python/src/pedro_agentware/reasoning/types.py.

export const CONTRACT_VERSION = "1";

export enum Format {
  NATIVE = "native",
  THINKING = "thinking",
  MODEL_SPECIFIC = "model_specific",
  NONE = "none",
}

// NodeKind is the closed vocabulary of context-tree node kinds.
export enum NodeKind {
  GOAL = "goal",
  OBSERVATION = "observation",
  DECISION = "decision",
  TOOL_CALL = "tool-call",
  TOOL_RESULT = "tool-result",
  CONCLUSION = "conclusion",
  BLOCKER = "blocker",
}

// NodeStatus is the closed vocabulary of context-tree node statuses.
export enum NodeStatus {
  ACTIVE = "active",
  COMPLETE = "complete",
  BLOCKED = "blocked",
  SUPERSEDED = "superseded",
}

// Node is a single node in the reasoning context tree. Nodes carry bounded
// summaries only; raw reasoning text never appears on a node.
export interface Node {
  id: string;
  parent_id: string;
  kind: NodeKind;
  status: NodeStatus;
  summary: string;
  evidence_refs: string[];
  tool_call_refs: string[];
  created_at: Date;
  updated_at: Date;
}

// ContextTree is the versioned, normalized representation of a model's
// reasoning. root_id points at the root node (the first node when the parser
// produced the tree); it is empty when no reasoning was detected.
export interface ContextTree {
  version: string;
  format: Format;
  model: string;
  backend: string;
  created_at: Date;
  root_id: string;
  nodes: Node[];
}

export function isContextTreeEmpty(tree: ContextTree | null | undefined): boolean {
  return !tree || tree.nodes.length === 0;
}

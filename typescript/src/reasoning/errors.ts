// Fail-closed errors raised by the reasoning adapter.
// Every error represents a fail-closed outcome: malformed or unbounded input
// never produces a partial tree or partially-stripped content.

export class ReasoningError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReasoningError";
  }
}

export class MalformedInputError extends ReasoningError {
  constructor(message: string) {
    super(message);
    this.name = "MalformedInputError";
  }
}

export class MalformedJSONError extends ReasoningError {
  constructor(message: string) {
    super(message);
    this.name = "MalformedJSONError";
  }
}

export class MalformedReasoningFieldError extends ReasoningError {
  constructor(message: string) {
    super(message);
    this.name = "MalformedReasoningFieldError";
  }
}

export class MalformedContentError extends ReasoningError {
  constructor(message: string) {
    super(message);
    this.name = "MalformedContentError";
  }
}

export class UnbalancedThinkingError extends ReasoningError {
  constructor(message = "reasoning: unbalanced thinking tag") {
    super(message);
    this.name = "UnbalancedThinkingError";
  }
}

export class ReasoningTooLargeError extends ReasoningError {
  constructor(message = "reasoning: reasoning exceeds maximum size") {
    super(message);
    this.name = "ReasoningTooLargeError";
  }
}

export class TooManyNodesError extends ReasoningError {
  constructor(message = "reasoning: too many reasoning nodes") {
    super(message);
    this.name = "TooManyNodesError";
  }
}

export class TooDeepError extends ReasoningError {
  constructor(message = "reasoning: reasoning tree too deep") {
    super(message);
    this.name = "TooDeepError";
  }
}

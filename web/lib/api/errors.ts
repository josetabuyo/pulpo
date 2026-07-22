import { ValidationError, ConflictError, NotFoundError } from "@/lib/business/bots";
import { PermissionDeniedError } from "@/lib/business/google-connections";

// Maps the business-layer error types (thrown the same way as the
// ValueError/KeyError/PermissionError distinctions in the Python routers)
// to HTTP responses, so route handlers stay thin.
export function errorResponse(err: unknown): Response {
  if (err instanceof NotFoundError) {
    return Response.json({ detail: err.message }, { status: 404 });
  }
  if (err instanceof ConflictError) {
    return Response.json({ detail: err.message }, { status: 409 });
  }
  if (err instanceof PermissionDeniedError) {
    return Response.json({ detail: err.message }, { status: 403 });
  }
  if (err instanceof ValidationError) {
    return Response.json({ detail: err.message }, { status: 400 });
  }
  throw err;
}

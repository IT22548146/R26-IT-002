import axios from "axios";

type ApiErrorBody = {
  error?: unknown;
  message?: unknown;
};

/** Return a safe user-facing message from an unknown request error. */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError<ApiErrorBody>(error)) return fallback;

  const body = error.response?.data;
  if (typeof body?.error === "string" && body.error.trim()) return body.error;
  if (typeof body?.message === "string" && body.message.trim()) return body.message;
  if (typeof error.message === "string" && error.message.trim()) return error.message;
  return fallback;
}

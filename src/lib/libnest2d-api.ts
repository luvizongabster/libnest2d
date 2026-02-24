/**
 * Client for the Libnest2D nesting API (nest-local).
 * Uses GET /jobs/:id?embed=result to get the result inline and avoid
 * fetching the presigned S3 URL (which can return non-JSON or fail CORS).
 */

export interface Libnest2dPlacement {
  instance_id: string;
  bin: number;
  x: number;
  y: number;
  rotation: number;
}

export interface Libnest2dResult {
  bins_used: number;
  placements: Libnest2dPlacement[];
  metrics?: { runtime_ms?: number; utilization?: number };
}

export interface Libnest2dJobStatus {
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  result_url?: string;
  expires_in_sec?: number;
  error?: string;
  /** Present when the API was called with ?embed=result and status is SUCCEEDED */
  result?: Libnest2dResult;
}

export interface PollOptions {
  /** When true, use GET /jobs/:id?embed=result so the response includes result inline. */
  embedResult?: boolean;
}

/**
 * Poll job status. When embedResult is true, uses GET /jobs/:id?embed=result
 * and the response may include result (bins_used, placements, metrics) inline.
 */
export async function pollLibnest2dJobStatus(
  baseUrl: string,
  jobId: string,
  intervalMs: number = 2000,
  options?: PollOptions
): Promise<Libnest2dJobStatus> {
  const url = options?.embedResult
    ? `${baseUrl.replace(/\/$/, "")}/jobs/${jobId}?embed=result`
    : `${baseUrl.replace(/\/$/, "")}/jobs/${jobId}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Libnest2D job status: ${res.status} ${res.statusText}`);
  }
  const data = await res.json();
  return data as Libnest2dJobStatus;
}

/**
 * Fetch the nesting result from a presigned result_url (S3/MinIO).
 * Use only as fallback when the API does not return result inline.
 */
export async function fetchLibnest2dResult(
  resultUrl: string
): Promise<Libnest2dResult> {
  const res = await fetch(resultUrl);
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Libnest2D result fetch: ${res.status} ${res.statusText}`);
  }
  try {
    return JSON.parse(text) as Libnest2dResult;
  } catch {
    throw new Error(
      "Buscar resultado do nesting libnest2d: Resposta não é JSON válido"
    );
  }
}

export interface RunLibnest2dNestingOptions {
  pollIntervalMs?: number;
}

/**
 * Submit a nesting job, poll until SUCCEEDED or FAILED, and return the result.
 * Uses embedResult: true so the result is returned inline from the API when
 * possible, avoiding a second request to result_url (and CORS/non-JSON errors).
 */
export async function runLibnest2dNesting(
  baseUrl: string,
  payload: Record<string, unknown>,
  options?: RunLibnest2dNestingOptions
): Promise<Libnest2dResult> {
  const createRes = await fetch(`${baseUrl.replace(/\/$/, "")}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!createRes.ok) {
    throw new Error(
      `Libnest2D create job: ${createRes.status} ${createRes.statusText}`
    );
  }
  const { job_id } = (await createRes.json()) as { job_id: string };
  const intervalMs = options?.pollIntervalMs ?? 2000;

  for (;;) {
    const status = await pollLibnest2dJobStatus(baseUrl, job_id, intervalMs, {
      embedResult: true,
    });

    if (status.status === "SUCCEEDED") {
      if (status.result && Array.isArray(status.result.placements)) {
        return status.result;
      }
      if (status.result_url) {
        return fetchLibnest2dResult(status.result_url);
      }
      throw new Error("Libnest2D: SUCCEEDED but no result or result_url");
    }

    if (status.status === "FAILED") {
      throw new Error(
        status.error ?? "Libnest2D job failed"
      );
    }

    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

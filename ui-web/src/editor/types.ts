/** Shared UI-only types for the editor (not part of the API contract, see api.ts). */

export type Tool = 'select' | 'brush' | 'segment';

export interface BusyState {
  op: string;
}

/** A point in project-canvas pixel space (post offset/fitScale conversion). */
export interface CanvasPoint {
  x: number;
  y: number;
}

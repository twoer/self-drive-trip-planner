export type TripLeg = {
  from: string;
  to: string;
};

export type TripDay = {
  day: string;
  title?: string;
  legs: TripLeg[];
  notes: string[];
};

export type ParseResponse = {
  ok: boolean;
  route_text: string;
  budget_text: string;
  days: TripDay[];
};

export type GenerateResponse = {
  ok: boolean;
  out_dir: string;
  output_url?: string | null;
  manifest_url: string;
  manifest: {
    title?: string;
    mode?: string;
    warnings?: string[];
    files?: Record<string, string>;
  };
};

export type EditorPayload = {
  title: string;
  start_date: string;
  mode: string;
  budget_text: string;
  days: TripDay[];
  pdf?: boolean;
};

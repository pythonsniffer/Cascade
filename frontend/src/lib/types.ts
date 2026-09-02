/** Types mirror backend/api/schemas.py, which mirrors 00_PROJECT_CONTEXT §5.
 *  No domain values live here — only shapes. */

export type Confidence = "high" | "low" | "warming_up";

export interface Provenance {
  real: string[];
  simulated: string[];
  assumed: string[];
  statement: string;
}

export type DetectorState = "ready" | "no_frames" | "no_detector";

export interface DetectorStatus {
  detector_loaded: boolean;
  detector_path: string;
  frames_available: number;
  frames_dir?: string;
  enabled: boolean;
  state: DetectorState;
  detail: string;
  error: string | null;
  chain_rules: number;
  min_lift: number;
}

export interface Health {
  status: string;
  models_loaded: boolean;
  models: {
    bottleneck: {
      loaded: boolean; ensemble_size: number; T_w: number;
      conf_threshold: number; n_stations: number; features: string[]; source: string;
    };
    defect: DetectorStatus;
    chains: { loaded: boolean; rules: number; min_lift: number; note: string };
  };
  mode: string;
  metrics: Metrics;
  provenance: Provenance;
  playing: boolean;
  tick_count: number;
  interval_s: number;
}

export interface Metrics {
  bottleneck?: {
    test_rmse: number;
    localization_within_2_all: number;
    localization_within_2_no_edge: number;
    n_bottleneck_test_shifts: number;
    baseline_persistence_rmse: number;
    baseline_moving_avg_rmse: number;
    source: string;
  };
  detector?: {
    mAP50: number; precision: number; recall: number; f1: number;
    test_images: number; train_images: number; source: string; note: string;
  };
  chains?: {
    planted: number; recovered: number; recovered_pairs: string[];
    history_vehicles: number; history_records: number; source: string;
  };
  /** the running detector's own numbers, read from best.pt at load time */
  detector_checkpoint?: {
    mAP50: number; mAP50_95?: number; precision: number; recall: number; f1?: number;
    source: string; note: string;
    train_imgsz?: number; train_epochs?: number; train_data?: string;
  };
}

export interface LineNode {
  station_id: number; zone: string; zone_label: string;
  sensor_poor: boolean; x: number; y: number;
}
export interface LineEdge {
  source: number; target: number; buffer: number; weight: number;
  kind: "serial" | "bypass" | "rework";
}
export interface Line {
  n_stations: number;
  zones: Record<string, { start: number; end: number; label: string }>;
  nodes: LineNode[];
  edges: LineEdge[];
  note: string;
}

export interface VisualDefect {
  station_id: number; zone: string; defect_class: string;
  confidence: number; bbox: number[];
}
export interface ProcessDefect { station_id: number; defect_type: string | null }
export interface ChainAlert {
  trigger_defect: string;
  predicted_downstream_defect: string;
  P_B_given_A: number;
  lift: number;
  origin_station: number;
  action: string;
  vehicle_id?: number;
  shift_id?: number;
  timestamp?: string;
}
export interface TwinState {
  vehicle_id: number;
  timestamp: string;
  shift_id?: number;
  bottleneck_station: number | null;
  bottleneck_zone: string | null;
  bottleneck_confidence: Confidence | null;
  bottleneck_abstained: boolean | null;
  visual_defects: VisualDefect[];
  process_defects: ProcessDefect[];
  downstream_inspection_alerts: ChainAlert[];
  _meta: Record<string, unknown>;
}

export interface BottleneckState {
  station: number | null;
  zone: string | null;
  confidence: Confidence;
  uncertainty: number | null;
  abstained: boolean;
  blk: number[] | null;
  stv: number[] | null;
}

export interface DefectEvent {
  shift_id: number; vehicle_id: number; station_id: number; timestamp: string;
  defect_class: string; defect_type: string | null; confidence: number;
  bbox: number[] | null; source: string; camera_id: string | null;
  station_source: string | null; frame: string | null; chains: ChainAlert[];
}

export interface PnLLineSource {
  status: "ok" | "missing_config";
  count_field: string;
  count: number;
  count_source?: "model_output";
  assumptions?: Record<string, number>;
  assumption_source?: "assumption";
  sign?: "credit" | "debit";
  formula?: string;
  missing?: string[];
}
export interface PnLResult {
  shift_id: number;
  counts: Record<string, number>;
  breakdown: Record<string, number | null>;
  net: number;
  sources: Record<string, PnLLineSource>;
  missing_config: string[];
  complete: boolean;
  currency: string;
  is_projection: boolean;
  disclaimer: string;
  cumulative?: number;
}
export interface PnL {
  latest: PnLResult | null;
  series: { shift_id: number; net: number; cumulative: number;
            breakdown: Record<string, number | null>; complete: boolean }[];
  cumulative_net: number;
  cumulative_breakdown: Record<string, number | null>;
  cumulative_counts: Record<string, number>;
  shifts_counted: number;
  assumptions: Record<string, number | null>;
  missing_config: string[];
  currency: string;
  is_projection: boolean;
  disclaimer: string;
  sensitivity: {
    key: string; base_value: number; pct: number;
    cumulative_low: number; cumulative_high: number; cumulative_base: number;
  } | null;
  last_changed: { at: string; actor: string; changes: Record<string, unknown> } | null;
}

export interface ShiftHistory {
  shift_id: number; shift_name: string;
  predicted_bottleneck_station: number | null;
  bottleneck_zone: string | null;
  confidence: Confidence; uncertainty: number | null; abstained: boolean;
  n_defect_events: number; n_chain_alerts: number;
  ground_truth_station: number | null; is_anomaly_shift: boolean;
}
export interface History {
  shifts: ShiftHistory[];
  pnl_series: PnL["series"];
  zone_counts: Record<string, number>;
  station_counts: Record<string, number>;
}

export interface ChainRule {
  trigger: string; downstream: string; P_B_given_A: number; lift: number;
}
export interface ConfigPayload {
  config: {
    line_config: any; model_config: any; mappings: any; pnl_config: any;
    paths: Record<string, string>;
  };
  provenance: Provenance;
  chains: ChainRule[];
  audits: { config_name: string; actor: string; created_at: string;
            changes: Record<string, any>; note: string | null }[];
}

/** WebSocket frames */
export interface TickMessage {
  type: "tick";
  shift_id: number;
  shift_name: string;
  tick_count: number;
  bottleneck: BottleneckState;
  twin_states: TwinState[];
  defect_events: DefectEvent[];
  new_alerts: ChainAlert[];
  pnl_delta: PnLResult;
  _meta: Record<string, any>;
}
export interface StatusMessage {
  type: "status";
  state: string;
  playing: boolean;
  interval_s: number;
  tick_count: number;
  defect_layer_enabled?: boolean;
  warming_up?: boolean;
}
export type WsMessage = TickMessage | StatusMessage | { type: "ping" };

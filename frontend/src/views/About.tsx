/** About (/about) — "what's real", rendered live from /health provenance (§5.6).
 *  This is the page you point a sceptical judge at. Nothing on it is typed by hand. */
import { SectionTitle } from "../components/primitives";
import { useTwin } from "../store/twin";

export function About() {
  const { health, line } = useTwin();
  if (!health) {
    return <div className="grid h-full place-items-center text-[13px] text-muted">Loading…</div>;
  }

  const p = health.provenance;
  const m = health.metrics;

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 lg:p-8">
      <header>
        <p className="eyebrow">The honest account</p>
        <h2 className="font-display text-[32px] font-light leading-tight tracking-tight">
          What is real, and what is simulated
        </h2>
        <p className="mt-3 border-l-2 border-accent pl-4 text-[14px] leading-relaxed">
          {p.statement}
        </p>
      </header>

      <Group title="Real — validated models and code" tone="real" items={p.real} />
      <Group title="Simulated — clearly labelled everywhere" tone="plain" items={p.simulated} />
      <Group title="Assumed — rule-based and documented" tone="plain" items={p.assumed} />

      <section>
        <SectionTitle>Measured numbers</SectionTitle>
        <div className="card-solid divide-y divide-hairline text-[12px]">
          {m.bottleneck && (
            <MetricRow
              name="Bottleneck forecaster (BSTAN)"
              source={m.bottleneck.source}
              detail={`Test RMSE ${m.bottleneck.test_rmse} against persistence ${
                m.bottleneck.baseline_persistence_rmse} and moving average ${
                m.bottleneck.baseline_moving_avg_rmse}. Localises within ±2 stations on ${
                (m.bottleneck.localization_within_2_all * 100).toFixed(0)}% of the ${
                m.bottleneck.n_bottleneck_test_shifts} bottleneck shifts in the test split, ${
                (m.bottleneck.localization_within_2_no_edge * 100).toFixed(0)}% excluding the
                first and last stations, which the Turning Point method cannot resolve.`}
            />
          )}
          {m.chains && (
            <MetricRow
              name="Defect-chain engine"
              source={m.chains.source}
              detail={`Recovered ${m.chains.recovered} of ${m.chains.planted} planted causal
                chains from ${m.chains.history_records.toLocaleString()} inspection records across
                ${m.chains.history_vehicles.toLocaleString()} vehicles: ${
                m.chains.recovered_pairs.join(", ")}.`}
            />
          )}
          {m.detector && (
            <MetricRow
              name="Defect detector (fine-tuned YOLOv8)"
              source={m.detector.source}
              warn={health.models.defect.state !== "ready"}
              detail={health.models.defect.detector_loaded
                ? `Loaded here and verified as the fine-tuned detector by matching its class names
                   against the configured list — a COCO model is refused. The checkpoint itself
                   records ${m.detector_checkpoint
                     ? `mAP50 ${m.detector_checkpoint.mAP50}, precision `
                       + `${m.detector_checkpoint.precision}, recall ${m.detector_checkpoint.recall}`
                     : "no metrics"}; the notebook separately reports mAP50 ${m.detector.mAP50} on
                   ${m.detector.test_images} real test images. ${health.models.defect.detail}`
                : `The detector weights are not loaded in this instance, so the camera layer is
                   off and produces no detections. Its published figures (mAP50 ${m.detector.mAP50}
                   on ${m.detector.test_images} test images) come from the notebook validation run
                   and are not claimed by this running instance.`}
            />
          )}
        </div>
      </section>

      <section>
        <SectionTitle>Why the line is fixed at {line?.n_stations ?? 35} stations</SectionTitle>
        <div className="card-solid space-y-3 p-4 text-[12.5px] leading-relaxed">
          <p>
            The forecaster is trained for this specific graph — its attention weights and
            normalisation are fitted to this topology. A different station count or wiring would
            need retraining, so fixing the line keeps the validated model valid exactly as it is.
          </p>
          <p className="text-muted">{line?.note}</p>
          <p>
            <span className="font-medium">Could this run on another line?</span> Topology is a
            graph. A different line means re-specifying nodes and edges and retraining the
            forecaster on that plant's data, seeded by FMEA knowledge for a cold start. We fixed{" "}
            {line?.n_stations ?? 35} for the prototype to keep the demo on the validated model.
            Other topologies are supported through retraining — that is the transfer-learning
            roadmap item, not something built here.
          </p>
          <p className="text-muted">
            The station count is never hardcoded in the interface: this floor plan is drawn from
            the topology the API serves, so the same code renders whatever graph it is given.
          </p>
        </div>
      </section>

      <section>
        <SectionTitle>How this instance is running</SectionTitle>
        <dl className="card-solid divide-y divide-hairline text-[12px]">
          <Row label="Forecaster">
            {health.models.bottleneck.ensemble_size} models loaded from artifacts, window{" "}
            {health.models.bottleneck.T_w} shifts. {health.models.bottleneck.source}
          </Row>
          <Row label="Detector">{health.models.defect.detail}</Row>
          <Row label="Chain engine">
            {health.models.chains.rules} rules above lift {health.models.chains.min_lift}.{" "}
            {health.models.chains.note}
          </Row>
          <Row label="Input stream">Simulator, mode “{health.mode}”</Row>
        </dl>
      </section>
    </div>
  );
}

function Group({ title, items, tone }: { title: string; items: string[]; tone: "real" | "plain" }) {
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      <ul className="space-y-2">
        {items.map((t, i) => (
          <li key={i}
              className={`rounded-card border p-3.5 text-[12.5px] leading-relaxed ${
                tone === "real" ? "border-hairline bg-white" : "border-hairline bg-black/[.02]"}`}>
            {t}
          </li>
        ))}
      </ul>
    </section>
  );
}

function MetricRow({ name, detail, source, warn }: {
  name: string; detail: string; source: string; warn?: boolean;
}) {
  return (
    <div className="p-3.5">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="font-display text-[13px] font-medium">{name}</span>
        <span className={`pill border font-mono text-[9px] ${
          warn ? "border-accent/30 bg-accent/[.06] text-accent"
               : "border-hairline bg-black/[.03] text-muted"}`}>
          {source}
        </span>
      </div>
      <p className="mt-1 leading-relaxed text-muted">{detail}</p>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 p-3.5">
      <dt className="w-[110px] shrink-0 text-muted">{label}</dt>
      <dd className="flex-1">{children}</dd>
    </div>
  );
}

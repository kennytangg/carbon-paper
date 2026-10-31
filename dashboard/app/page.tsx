import { Accuracy, Clouds, Confidence, Crediting, GroundTruth, Method, Overview, Sequestration } from "@/components/sections";
import { ThemeToggle } from "@/components/ThemeToggle";

const NAV = [
  ["overview", "Overview"],
  ["accuracy", "Accuracy"],
  ["ground-truth", "Ground truth"],
  ["clouds", "Clouds"],
  ["confidence", "Confidence"],
  ["crediting", "Crediting"],
  ["sequestration", "Growth"],
  ["method", "Method"],
] as const;

export default function Page() {
  return (
    <>
      <header className="top">
        <div className="wrap">
          <div className="top-row">
            <div>
              <div className="eyebrow">NusaCarbon · BINUS research</div>
              <h1>Satellite vs Ground Truth</h1>
            </div>
            <ThemeToggle />
          </div>
          <p className="lede">
            Can satellites replace the field plot? A blind benchmark of open satellite data against the standard field formula for forest carbon, on 475
            plots from Indonesia, Gabon, French Guiana and a pantropical network, with honest intervals, clouds measured at each plot, and a crediting rule
            with a calibrated over-crediting risk.
          </p>
        </div>
      </header>
      <nav className="nav" aria-label="Sections">
        <div className="wrap">
          {NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`}>
              {label}
            </a>
          ))}
        </div>
      </nav>
      <main>
        <Overview />
        <Accuracy />
        <GroundTruth />
        <Clouds />
        <Confidence />
        <Crediting />
        <Sequestration />
        <Method />
      </main>
      <footer>
        <div className="wrap">
          <div>
            <b style={{ color: "var(--text-primary)" }}>Kenny Tang, Riki Awal Syahputra, Richard Hans</b> · Computer Science Department, Bina Nusantara
            University, Jakarta
          </div>
          <div>
            Paper and code:{" "}
            <a href="https://github.com/kennytangg/carbon-paper" target="_blank" rel="noreferrer">
              github.com/kennytangg/carbon-paper
            </a>
            . Every number on this page is read from <code>data/estimation/results/</code> by <code>dashboard/scripts/export_data.py</code>.
          </div>
          <div>
            Field data: HCSA Indonesia, GEO-TREES (IIASA), Labrière et al. 2018, SAFE project (Sabah). Satellite data: Copernicus Sentinel-1/2, Landsat,
            ALOS PALSAR, GEDI, Meta and ETH canopy height, ESA CCI Biomass, Hansen Global Forest Change, via Google Earth Engine.
          </div>
        </div>
      </footer>
    </>
  );
}

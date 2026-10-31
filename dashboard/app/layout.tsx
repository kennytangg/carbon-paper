import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NusaCarbon — Satellite vs Ground Truth",
  description:
    "Blind benchmark of satellite-only forest carbon estimates against standard-formula field ground truth: accuracy, clouds, confidence and conformal crediting.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

// Applies a saved light/dark choice before first paint; falls back to the OS setting.
const themeScript = `try{var t=localStorage.getItem("nc-theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

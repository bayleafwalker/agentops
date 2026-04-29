import "./globals.css";

export const metadata = {
  title: "agentops",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

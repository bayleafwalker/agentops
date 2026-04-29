export function DegradedSourceBanner({ message }) {
  if (!message) {
    return null;
  }
  return <div className="banner">{message}</div>;
}

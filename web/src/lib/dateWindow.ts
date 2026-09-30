export function isoWindowForInclusiveDateRange(range: {
  from: Date;
  to: Date;
}): { from: string; to: string } {
  const from = new Date(
    Date.UTC(
      range.from.getFullYear(),
      range.from.getMonth(),
      range.from.getDate()
    )
  );
  const to = new Date(
    Date.UTC(
      range.to.getFullYear(),
      range.to.getMonth(),
      range.to.getDate() + 1
    )
  );
  return { from: from.toISOString(), to: to.toISOString() };
}

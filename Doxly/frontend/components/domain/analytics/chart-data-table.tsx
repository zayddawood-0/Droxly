import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { TimeSeriesPoint } from "@/lib/api/analytics";

/**
 * ui-ux.md §13 — "charts have a text/table equivalent or accessible
 * summary for screen-reader users, not visual-only data." Visually hidden
 * (the chart is the visual presentation); exposes the identical series as
 * a real table for assistive tech.
 */
export function ChartDataTable({
  caption,
  data,
}: {
  caption: string;
  data: TimeSeriesPoint[];
}) {
  return (
    <div className="sr-only">
      <Table>
        <caption className="sr-only">{caption}</caption>
        <TableHeader>
          <TableRow>
            <TableHead>Date</TableHead>
            <TableHead>Count</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((point) => (
            <TableRow key={point.date}>
              <TableCell>{point.date}</TableCell>
              <TableCell>{point.count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

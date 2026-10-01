import type { ReactNode } from "react";

export type Column<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  width?: string;
  align?: "left" | "right";
};

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  selectedKey?: string | number | null;
  dense?: boolean;
};

export function DataTable<T>({ columns, rows, rowKey, empty, onRowClick, selectedKey, dense }: Props<T>) {
  if (!rows.length && empty) return <>{empty}</>;
  return (
    <div className="table-wrap">
      <table className={`data-table${dense ? " dense" : ""}`}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} style={{ width: column.width, textAlign: column.align ?? "left" }}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            return (
              <tr
                key={key}
                className={`${onRowClick ? "clickable" : ""}${selectedKey === key ? " selected" : ""}`}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((column) => (
                  <td key={column.key} style={{ textAlign: column.align ?? "left" }}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

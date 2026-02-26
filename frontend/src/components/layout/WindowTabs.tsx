import Link from "next/link";

import { TimeWindow, WINDOW_OPTIONS } from "@/lib/api";

type Props = {
  pathname: string;
  active: TimeWindow;
};

export default function WindowTabs({ pathname, active }: Props) {
  return (
    <div className="windowTabs">
      {WINDOW_OPTIONS.map((option) => {
        const isActive = option === active;
        return (
          <Link
            key={option}
            href={{ pathname, query: { window: option } }}
            className={isActive ? "windowTab active" : "windowTab"}
          >
            {option}
          </Link>
        );
      })}
    </div>
  );
}

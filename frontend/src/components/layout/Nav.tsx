"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "概览" },
  { href: "/capital-flow", label: "资金流" },
  { href: "/structure-risk", label: "结构风险" },
  { href: "/macro", label: "宏观" },
  { href: "/metrics", label: "指标详情" },
  { href: "/disclaimer", label: "免责声明" }
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="nav">
      <div className="navBrand">BTC Observer</div>
      <div className="navLinks">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={pathname === link.href ? "active" : ""}
          >
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

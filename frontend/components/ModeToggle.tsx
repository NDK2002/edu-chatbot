"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function ModeToggle() {
  const pathname = usePathname();
  const isStudent = pathname.startsWith("/student");

  return (
    <div className="flex items-center gap-2">
      {isStudent ? (
        <Link
          href="/teacher"
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-xl font-semibold text-sm hover:bg-emerald-700 transition-colors shadow"
        >
          <span className="text-lg">👩‍🏫</span>
          Chế độ Giáo viên
        </Link>
      ) : (
        <Link
          href="/student"
          className="flex items-center gap-2 px-4 py-2 bg-sky-500 text-white rounded-xl font-semibold text-sm hover:bg-sky-600 transition-colors shadow"
        >
          <span className="text-lg">🎒</span>
          Chế độ Học sinh
        </Link>
      )}
    </div>
  );
}

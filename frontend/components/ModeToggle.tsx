"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";

export default function ModeToggle() {
  const pathname = usePathname();
  const isStudent = pathname.startsWith("/student");

  return (
    <div className="flex items-center">
      {isStudent ? (
        <Link
          href="/teacher"
          className="inline-flex items-center justify-center gap-2 w-44 h-9 bg-emerald-600 text-white rounded-xl font-semibold text-sm hover:bg-emerald-700 transition-colors shadow"
        >
          <Image src="/teacher-icon.png" alt="Giáo viên" width={20} height={20} />
          Chế độ Giáo viên
        </Link>
      ) : (
        <Link
          href="/student"
          className="inline-flex items-center justify-center gap-2 w-44 h-9 bg-sky-500 text-white rounded-xl font-semibold text-sm hover:bg-sky-600 transition-colors shadow"
        >
          <Image src="/student-icon.png" alt="Học sinh" width={20} height={20} />
          Chế độ Học sinh
        </Link>
      )}
    </div>
  );
}

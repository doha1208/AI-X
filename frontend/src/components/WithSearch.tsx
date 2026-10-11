"use client";

import { Suspense, type ComponentType } from "react";
import { useSearchParams } from "next/navigation";

type SearchProps = { search: string };

// 페이지가 처음 그려질 때 쓸 URL 쿼리를 넘긴다. router.push로 넘어온 직후의 첫 렌더에서는
// window.location이 아직 이전 페이지 주소라서, 라우터가 알고 있는 쿼리(useSearchParams)를 쓴다.
export function withSearch(Page: ComponentType<SearchProps>) {
  function SearchReader() {
    const params = useSearchParams();
    return <Page search={`?${params.toString()}`} />;
  }
  return function PageWithSearch() {
    return (
      <Suspense fallback={null}>
        <SearchReader />
      </Suspense>
    );
  };
}

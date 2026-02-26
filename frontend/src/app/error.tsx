"use client";

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <section className="contentCard">
      <h1>页面加载失败</h1>
      <p>后端可能尚未完成初始化，或接口暂时不可用。</p>
      <button className="retryBtn" type="button" onClick={() => reset()}>
        重试
      </button>
    </section>
  );
}

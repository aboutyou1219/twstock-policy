import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="min-h-screen">
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 grid-noise opacity-20" />
        <div className="absolute -top-24 right-[-120px] h-72 w-72 rounded-full bg-coral/30 blur-3xl" />
        <div className="absolute top-52 left-[-160px] h-80 w-80 rounded-full bg-teal/30 blur-3xl" />

        <section className="relative mx-auto flex max-w-6xl flex-col gap-10 px-6 py-24">
          <div className="flex flex-col gap-4">
            <span className="w-fit rounded-full border border-white/20 px-4 py-1 text-xs uppercase tracking-[0.3em] text-white/70">
              YAHOO MVP
            </span>
            <h1 className="text-4xl font-semibold leading-tight md:text-6xl">
              快速篩選台股體質
              <span className="block text-sand">毛利率・營益率・ROI・股本</span>
            </h1>
            <p className="max-w-2xl text-base text-white/70 md:text-lg">
              以 Yahoo 月營收爬蟲為核心，先做一個能跑、能查、能用的資料儀表板。
              你可以依產業、規模與指標區間快速篩出觀察名單。
            </p>
          </div>

          <div className="flex flex-wrap gap-4">
            <Button>開始篩選</Button>
            <Button variant="ghost">查看資料流程</Button>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            {[
              {
                title: "指標ETL",
                desc: "收入、毛利、營業利益計算指標，保留原始財報。",
              },
              {
                title: "可擴展API",
                desc: "FastAPI + PostgreSQL，為篩選與排序提供可靠查詢。",
              },
              {
                title: "視覺化篩選",
                desc: "Next.js + Tailwind，打造敏捷操作介面。",
              },
            ].map((item) => (
              <div
                key={item.title}
                className="rounded-2xl border border-white/10 bg-white/5 p-6 backdrop-blur"
              >
                <h3 className="text-lg font-semibold text-white">{item.title}</h3>
                <p className="mt-2 text-sm text-white/70">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

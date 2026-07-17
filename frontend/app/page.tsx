import type { Metadata } from "next";
import { MuseLensApp } from "./MuseLensApp";

export const metadata: Metadata = {
  title: "MuseLens · 语义图片搜索",
  description: "使用自然语言探索你的本地图片库。",
};

export default function Home() {
  return <MuseLensApp />;
}

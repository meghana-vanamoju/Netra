import { Composition } from "remotion";
import { NetraShowcase } from "./NetraShowcase";
export const RemotionRoot = () => (
  <Composition id="NetraShowcase" component={NetraShowcase} durationInFrames={300} fps={30} width={1920} height={1080} />
);

import WeatherWidget from "./widgets/WeatherWidget";
import DockerWidget from "./widgets/DockerWidget";
import SystemWidget from "./widgets/SystemWidget";

export default function WidgetArc() {
  return (
    <div className="widget-arc">
      <div className="widget-arc__item widget-arc__item--left">
        <WeatherWidget />
      </div>
      <div className="widget-arc__item widget-arc__item--center">
        <DockerWidget />
      </div>
      <div className="widget-arc__item widget-arc__item--right">
        <SystemWidget />
      </div>
    </div>
  );
}

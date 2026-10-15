import { createElement, lazy } from 'react';
import * as Icons from 'lucide-react';
import { CENTURY_FEATURES } from './centuryCatalog';

const PAGE_FILES = import.meta.glob([
    '../pages/Insights.jsx', '../pages/Gym.jsx', '../pages/Cards.jsx',
    '../pages/Placements.jsx', '../pages/OA.jsx', '../pages/Interview.jsx', '../pages/Mistakes.jsx',
    '../pages/Weekly.jsx', '../pages/Pace.jsx', '../pages/Unstuck.jsx',
    '../pages/Agents.jsx', '../pages/Speedrun.jsx', '../pages/Bounties.jsx', '../pages/Arena.jsx', '../pages/Drillmaster.jsx',
    '../pages/Dempsey.jsx', '../pages/Radar.jsx', '../pages/Ghost.jsx', '../pages/Forge.jsx', '../pages/HotSeat.jsx',
    '../pages/Century.jsx', '../pages/BugHunt.jsx', '../pages/Complexity.jsx', '../pages/Lofi.jsx',
    '../pages/ATS.jsx', '../pages/ArchSim.jsx', '../pages/JobRadar.jsx',
]);

const COMPONENT_FILES = import.meta.glob([
    '../components/InsightsCard.jsx', '../components/BriefCard.jsx', '../components/RingsCard.jsx',
    '../components/BossCard.jsx', '../components/HabitsCard.jsx', '../components/CardsCard.jsx',
    '../components/PlacementsCard.jsx', '../components/QuickCapture.jsx',
    '../components/AgentSwarmCard.jsx', '../components/SpeedrunCard.jsx', '../components/BountiesCard.jsx',
    '../components/ArenaCard.jsx', '../components/DrillmasterCard.jsx',
    '../components/DempseyCard.jsx', '../components/RadarCard.jsx',
    '../components/GhostCard.jsx', '../components/ForgeCard.jsx', '../components/HotSeatCard.jsx',
    '../components/CenturyCard.jsx', '../components/BugHuntCard.jsx', '../components/ComplexityCard.jsx', '../components/LofiCard.jsx',
    '../components/ATSCard.jsx', '../components/ArchSimCard.jsx', '../components/JobRadarCard.jsx',
]);

const lazyFrom = (files, name) => {
    const loader = files[name];
    return loader ? lazy(loader) : null;
};
const page = (name) => lazyFrom(PAGE_FILES, `../pages/${name}.jsx`);
const comp = (name) => lazyFrom(COMPONENT_FILES, `../components/${name}.jsx`);

const DynamicFeatureViewer = lazy(() => import('../components/DynamicFeatureViewer'));

/**
 * The Master 100 Features Registry.
 * Powers the Beta Lab, Navigation, Today Widgets, and dynamic routing across all 7 epic domains.
 */
export const FEATURES = CENTURY_FEATURES.map((f) => {
    let pageComp = f.dedicatedPage ? page(f.dedicatedPage) : null;
    if (!pageComp) {
        pageComp = function ViewerWrapper(props) {
            return createElement(DynamicFeatureViewer, {
                featureId: f.id,
                title: f.label,
                domain: f.domain,
                desc: f.desc,
                defaultXp: f.xp || 75,
                ...props,
            });
        };
    }

    const cardComp = f.dedicatedCard ? comp(f.dedicatedCard) : null;
    const IconComp = Icons[f.icon] || Icons.Sparkles;

    return {
        id: f.id,
        label: f.label,
        domain: f.domain,
        desc: f.desc,
        icon: IconComp,
        page: pageComp,
        cards: cardComp ? [cardComp] : [],
        available: true,
    };
});

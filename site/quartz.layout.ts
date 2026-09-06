import { PageLayout, SharedLayout } from "./quartz/cfg";
import * as Component from "./quartz/components";

const repository = process.env.GITHUB_REPOSITORY;
const repositoryUrl = repository
  ? `https://github.com/${repository}`
  : "https://github.com";

export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [],
  afterBody: [],
  footer: Component.Footer({ links: { "Source repository": repositoryUrl } }),
};

export const defaultContentPageLayout: PageLayout = {
  beforeBody: [
    Component.Breadcrumbs(),
    Component.ArticleTitle(),
    Component.ContentMeta(),
  ],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        { Component: Component.Search(), grow: true },
        { Component: Component.Darkmode() },
        { Component: Component.ReaderMode() },
      ],
    }),
    Component.Explorer({
      folderDefaultState: "collapsed",
      filterFn: (node) =>
        !["inbox", "raw", "_meta", "_archive"].includes(node.slugSegment),
    }),
  ],
  right: [
    Component.DesktopOnly(Component.TableOfContents()),
    Component.Backlinks(),
  ],
};

export const defaultListPageLayout: PageLayout = {
  beforeBody: [
    Component.Breadcrumbs(),
    Component.ArticleTitle(),
    Component.ContentMeta(),
  ],
  left: [Component.PageTitle(), Component.Explorer()],
  right: [],
};
